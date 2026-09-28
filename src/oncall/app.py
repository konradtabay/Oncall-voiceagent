"""FastAPI app: alerts, Twilio webhooks, and the ElevenLabs custom LLM."""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from oncall.config import Settings
from oncall.env_loader import load_dotenv
from oncall.incident.machine import Machine
from oncall.incident.service import IncidentService, sse_bytes
from oncall.incident.store import Store
from oncall.telephony.router import bind, router


def create_app(
    service: IncidentService | None = None,
    *,
    auth_token: str | None = None,
    public_base_url: str = "",
    alert_token: str = "",
) -> FastAPI:
    app = FastAPI(title="On-call voice")
    app.include_router(router)
    if service is not None:
        app.state.service = service
        base = public_base_url.strip().rstrip("/")
        bind(
            service.telephony,
            auth_token,
            public_base_url=base or None,
        )
    app.state.alert_token = alert_token

    def _alert_auth_ok(request: Request) -> bool:
        token = getattr(app.state, "alert_token", "") or ""
        if not token:
            return True
        header = request.headers.get("authorization") or ""
        if header.lower().startswith("bearer "):
            return header[7:].strip() == token
        return False

    @app.post("/alerts")
    async def alerts(request: Request) -> JSONResponse:
        if not _alert_auth_ok(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        current: IncidentService = request.app.state.service
        number = str(
            body.get("to_number")
            or os.environ.get("MAINTAINER_NUMBER")
            or ""
        )
        if not number:
            return JSONResponse({"error": "no to_number or MAINTAINER_NUMBER"}, status_code=400)
        incident = current.open_alert(
            summary=str(body.get("summary") or ""),
            logs=str(body.get("logs") or ""),
            verify_target=str(body.get("verify_target") or ""),
            to_number=number,
            incident_id=body.get("incident_id"),
        )
        return JSONResponse({"incident_id": incident.id, "state": incident.state})

    @app.get("/incidents/{incident_id}/transcript")
    async def incident_transcript(incident_id: str, request: Request) -> dict:
        current: IncidentService = request.app.state.service
        row = current.transcript_for(incident_id)
        if row is None:
            return {"incident_id": incident_id, "transcript": None}
        return row

    @app.post("/elevenlabs/phase")
    async def elevenlabs_phase(request: Request) -> JSONResponse:
        body = await request.json()
        params = body.get("parameters") if isinstance(body.get("parameters"), dict) else body
        current: IncidentService = request.app.state.service
        result = current.on_voice_phase(
            value=str(params.get("value") or ""),
            issue=str(params.get("issue") or ""),
            solution=str(params.get("solution") or ""),
            incident_id=str(params.get("incident_id") or ""),
        )
        return JSONResponse(result)

    @app.post("/elevenlabs/updates")
    async def elevenlabs_updates(request: Request) -> JSONResponse:
        body = await request.json()
        params = body.get("parameters") if isinstance(body.get("parameters"), dict) else body
        current: IncidentService = request.app.state.service
        incident_id = current.resolve_voice_incident(
            str(params.get("incident_id") or "")
        )
        timeout = 55.0
        text = current.ready_voice_update(incident_id)
        if not text and incident_id:
            text = current.wait_voice_update(incident_id, timeout=timeout)
        if not text:
            text = current.ready_voice_update(incident_id)
        if not text:
            return JSONResponse(
                {
                    "update": "",
                    "result": (
                        "No update yet. Say nothing and call updates again. "
                        "Keep calling updates until you get the fix result text. "
                        "If they just asked you something, answer that, then call updates again."
                    ),
                }
            )
        return JSONResponse(
            {
                "update": text,
                "result": (
                    f"You must speak this out loud now, every sentence, ending with the last one: {text} "
                    "Do not skip_turn. This is the fix completing."
                ),
            }
        )

    @app.post("/v1/chat/completions/chat/completions")
    async def chat_completions_doubled(request: Request) -> StreamingResponse:
        return await chat_completions(request)

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> StreamingResponse:
        body = await request.json()
        current: IncidentService = request.app.state.service
        messages = body.get("messages") or []
        return StreamingResponse(
            sse_bytes(current.completion(messages)),
            media_type="text/event-stream",
        )

    return app


def build_default_app() -> FastAPI:
    load_dotenv()
    settings = Settings.from_env()
    store = Store(settings.database_path)
    machine = Machine(store)
    from oncall.agents.factory import build_implementer
    from oncall.telephony.adapters import ElevenLabsRegisterAdapter, TwilioRestAdapter
    from oncall.telephony.service import Telephony

    implementer = build_implementer(settings)
    twilio = TwilioRestAdapter(
        settings.twilio_account_sid,
        settings.twilio_auth_token,
        machine_detection=settings.twilio_machine_detection or None,
    )

    def _call_context(incident_id: str) -> dict[str, str]:
        return service_box["service"].call_context(incident_id)

    eleven = ElevenLabsRegisterAdapter(
        settings.elevenlabs_api_key,
        settings.elevenlabs_agent_id,
        context_for=_call_context,
    )
    service_box: dict[str, IncidentService] = {}

    def on_event(event):  # type: ignore[no-untyped-def]
        return service_box["service"].handle_event(event)

    telephony = Telephony(
        twilio,
        eleven,
        settings.twilio_auth_token,
        on_event,
        from_number=settings.twilio_from_number,
        voice_url=f"{settings.public_base_url}/twilio/voice",
        status_url=f"{settings.public_base_url}/twilio/status",
        public_base_url=settings.public_base_url,
    )
    service = IncidentService(
        store,
        machine,
        implementer,
        telephony,
        repo_url=settings.repo_url,
        elevenlabs_api_key=settings.elevenlabs_api_key,
        diagnose_timeout_secs=settings.diagnose_timeout_secs,
    )
    service_box["service"] = service
    return create_app(
        service,
        auth_token=settings.twilio_auth_token,
        public_base_url=settings.public_base_url,
        alert_token=settings.alert_token,
    )
