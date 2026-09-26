"""FastAPI app: alerts, Twilio webhooks, and the ElevenLabs custom LLM."""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from oncall.config import Settings
from oncall.incident.machine import Machine
from oncall.incident.service import IncidentService, sse_bytes
from oncall.incident.store import Store
from oncall.telephony.router import bind, router


def _load_dotenv() -> None:
    from pathlib import Path

    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def create_app(
    service: IncidentService | None = None,
    *,
    auth_token: str | None = None,
    public_base_url: str = "",
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

    @app.post("/alerts")
    async def alerts(request: Request) -> dict:
        body = await request.json()
        current: IncidentService = request.app.state.service
        number = body.get("to_number") or ""
        incident = current.open_alert(
            summary=str(body.get("summary") or ""),
            logs=str(body.get("logs") or ""),
            verify_target=str(body.get("verify_target") or ""),
            to_number=str(number),
            incident_id=body.get("incident_id"),
        )
        return {"incident_id": incident.id, "state": incident.state}

    @app.post("/elevenlabs/phase")
    async def elevenlabs_phase(request: Request) -> JSONResponse:
        """Webhook tool for the ElevenLabs conversation agent."""
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

    @app.post("/v1/chat/completions/chat/completions")
    async def chat_completions_doubled(request: Request) -> StreamingResponse:
        """Some ElevenLabs configs POST here when the agent URL includes /chat/completions."""
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
    """Wire live Twilio, ElevenLabs, and Cursor clients from the environment."""
    _load_dotenv()
    settings = Settings.from_env()
    store = Store(settings.database_path)
    machine = Machine(store)
    from oncall.incident.cursor_client import HttpCursorClient
    from oncall.telephony.adapters import ElevenLabsRegisterAdapter, TwilioRestAdapter
    from oncall.telephony.service import Telephony

    twilio = TwilioRestAdapter(
        settings.twilio_account_sid,
        settings.twilio_auth_token,
        machine_detection=settings.twilio_machine_detection or None,
    )
    def _call_context(incident_id: str) -> dict[str, str]:
        row = store.get(incident_id)
        if row is None:
            return {}
        return {"brief": row.brief, "fix": row.fix}

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
    )
    service = IncidentService(
        store,
        machine,
        HttpCursorClient(
            settings.cursor_api_key,
            busy_wait=5.0,
            max_busy_retries=25,
        ),
        telephony,
        repo_url=settings.cursor_repo_url,
    )
    service_box["service"] = service
    return create_app(
        service,
        auth_token=settings.twilio_auth_token,
        public_base_url=settings.public_base_url,
    )
