"""Real Twilio and ElevenLabs adapters. Tests must not construct these."""

from __future__ import annotations

import os
from typing import Any


class TwilioRestAdapter:
    """Twilio REST client adapter.

    ``create_call`` always passes ``MachineDetection=Enable`` so AMD
    results arrive on the voice webhook as ``AnsweredBy``.
    """

    def __init__(
        self,
        account_sid: str | None = None,
        auth_token: str | None = None,
        *,
        machine_detection: str | None = None,
    ) -> None:
        sid = account_sid or os.environ["TWILIO_ACCOUNT_SID"]
        token = auth_token or os.environ["TWILIO_AUTH_TOKEN"]
        from twilio.rest import Client

        self._client = Client(sid, token)
        # Only outbound calls from this app; unset = no AMD (Twilio console cannot scope AMD per number for API dials).
        raw = machine_detection if machine_detection is not None else os.environ.get(
            "TWILIO_MACHINE_DETECTION", ""
        )
        self._machine_detection = raw.strip() or None

    def create_call(
        self,
        to: str,
        from_: str,
        voice_url: str,
        status_url: str,
    ) -> str:
        kwargs: dict[str, Any] = {
            "to": to,
            "from_": from_,
            "url": voice_url,
            "status_callback": status_url,
        }
        if self._machine_detection:
            kwargs["machine_detection"] = self._machine_detection
        call = self._client.calls.create(**kwargs)
        return call.sid

    def hangup(self, call_sid: str) -> None:
        self._client.calls(call_sid).update(status="completed")

    def send_sms(self, to: str, from_: str, body: str) -> None:
        self._client.messages.create(to=to, from_=from_, body=body)


class ElevenLabsRegisterAdapter:
    """POSTs to ElevenLabs convai Twilio register-call."""

    REGISTER_URL = "https://api.elevenlabs.io/v1/convai/twilio/register-call"

    def __init__(
        self,
        api_key: str | None = None,
        agent_id: str | None = None,
        http_client: Any | None = None,
        context_for: Any | None = None,
    ) -> None:
        self._api_key = api_key or os.environ["ELEVENLABS_API_KEY"]
        self._agent_id = agent_id or os.environ.get("ELEVENLABS_AGENT_ID", "")
        self._http = http_client
        self._context_for = context_for

    def register_call(
        self,
        incident_id: str,
        from_number: str,
        to_number: str,
    ) -> str:
        import httpx

        client = self._http or httpx
        context: dict[str, str] = {}
        if self._context_for is not None:
            loaded = self._context_for(incident_id) or {}
            context = {str(k): str(v) for k, v in loaded.items()}
        payload: dict[str, Any] = {
            "from_number": from_number,
            "to_number": to_number,
            "conversation_initiation_client_data": {
                "dynamic_variables": {
                    "incident_id": incident_id,
                    "brief": context.get("brief", "")[:1500],
                    "fix": context.get("fix", "")[:800],
                },
            },
        }
        if self._agent_id:
            payload["agent_id"] = self._agent_id
        response = client.post(
            self.REGISTER_URL,
            headers={"xi-api-key": self._api_key},
            json=payload,
        )
        response.raise_for_status()
        return response.text
