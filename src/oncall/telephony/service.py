"""Telephony service: dial, webhooks, hangup, SMS."""

from __future__ import annotations

from typing import Callable
from urllib.parse import quote

from fastapi.responses import Response

from oncall.seam import (
    Answered,
    Dial,
    Hangup,
    Missed,
    MissReason,
    SmsIn,
    SmsOut,
)
from oncall.telephony.ports import ElevenLabsPort, TwilioPort

HANGUP_TWIML = "<Response><Hangup/></Response>"
MISS_STATUSES = frozenset({"no-answer", "busy", "failed", "canceled"})
ANSWER_STATUSES = frozenset({"in-progress", "answered"})
HANGUP_REASONS = frozenset({"close", "miss", "drop"})

OnEvent = Callable[[Answered | Missed | SmsIn], str | None]


class BadSignature(Exception):
    """Raised when a Twilio webhook signature is invalid."""


def twiml_hangup() -> Response:
    return Response(content=HANGUP_TWIML, media_type="application/xml")


def twiml_body(body: str) -> Response:
    return Response(content=body, media_type="application/xml")


class Telephony:
    def __init__(
        self,
        twilio_port: TwilioPort,
        elevenlabs_port: ElevenLabsPort,
        validator: str | None,
        on_event: OnEvent,
        *,
        from_number: str = "",
        voice_url: str = "",
        status_url: str = "",
    ) -> None:
        self.twilio_port = twilio_port
        self.elevenlabs_port = elevenlabs_port
        self.validator = validator
        self.on_event = on_event
        self.from_number = from_number
        self.voice_url = voice_url
        self.status_url = status_url
        self._by_sid: dict[str, str] = {}
        self._sid_by_incident: dict[str, str] = {}
        self._to_by_incident: dict[str, str] = {}

    def dial(self, command: Dial) -> str:
        voice_url = self._url_with_incident(self.voice_url, command.incident_id)
        status_url = self._url_with_incident(self.status_url, command.incident_id)
        call_sid = self.twilio_port.create_call(
            to=command.to_number,
            from_=self.from_number,
            voice_url=voice_url,
            status_url=status_url,
        )
        self._by_sid[call_sid] = command.incident_id
        self._sid_by_incident[command.incident_id] = call_sid
        self._to_by_incident[command.incident_id] = command.to_number
        return call_sid

    def hangup(self, command: Hangup) -> None:
        if command.reason not in HANGUP_REASONS:
            return
        call_sid = self._sid_by_incident.get(command.incident_id)
        if call_sid is None:
            return
        self.twilio_port.hangup(call_sid)

    def sms_out(self, command: SmsOut) -> None:
        to = self._to_by_incident.get(command.incident_id, "")
        self.twilio_port.send_sms(
            to=to,
            from_=self.from_number,
            body=command.body,
        )

    def handle_voice(self, form: dict, signature_ok: bool) -> Response:
        if not signature_ok:
            raise BadSignature()

        call_sid = str(form.get("CallSid") or "")
        # Only calls created by dial(), or Twilio calling back our dial URL, are answered.
        incident_id = self._by_sid.get(call_sid)
        if incident_id is None:
            hinted = str(form.get("incident_id") or "")
            if hinted and hinted in self._to_by_incident:
                incident_id = hinted
                if call_sid:
                    self._by_sid[call_sid] = incident_id
                    self._sid_by_incident[incident_id] = call_sid
        if incident_id is None:
            return twiml_hangup()

        answered_by = str(form.get("AnsweredBy") or "").lower()
        call_status = str(form.get("CallStatus") or "").lower()

        if answered_by.startswith("machine") or call_status in MISS_STATUSES:
            reason: MissReason
            if answered_by.startswith("machine"):
                reason = "machine"
            else:
                reason = call_status  # type: ignore[assignment]
            self.on_event(Missed(incident_id=incident_id, reason=reason))
            return twiml_hangup()

        if answered_by == "human" or call_status in ANSWER_STATUSES:
            twiml = self.elevenlabs_port.register_call(
                incident_id,
                str(form.get("From") or ""),
                str(form.get("To") or ""),
            )
            self.on_event(Answered(incident_id=incident_id, call_sid=call_sid))
            return twiml_body(twiml)

        return twiml_hangup()

    def handle_status(self, form: dict, signature_ok: bool) -> None:
        if not signature_ok:
            raise BadSignature()

        call_sid = str(form.get("CallSid") or "")
        incident_id = self._resolve_incident(call_sid, form)
        if incident_id is None:
            return

        answered_by = str(form.get("AnsweredBy") or "").lower()
        call_status = str(form.get("CallStatus") or "").lower()

        if answered_by.startswith("machine"):
            self.on_event(Missed(incident_id=incident_id, reason="machine"))
            return

        if call_status in MISS_STATUSES:
            self.on_event(
                Missed(incident_id=incident_id, reason=call_status)  # type: ignore[arg-type]
            )
            return

        # completed and other statuses: ignore

    def handle_sms(self, form: dict, signature_ok: bool) -> str | None:
        if not signature_ok:
            raise BadSignature()
        return self.on_event(
            SmsIn(
                from_number=str(form.get("From") or ""),
                body=str(form.get("Body") or ""),
            )
        )

    def _resolve_incident(self, call_sid: str, form: dict) -> str | None:
        if call_sid and call_sid in self._by_sid:
            return self._by_sid[call_sid]
        incident = form.get("incident_id") or form.get("incident")
        if incident:
            return str(incident)
        return None

    @staticmethod
    def _url_with_incident(base: str, incident_id: str) -> str:
        if not base:
            return base
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}incident_id={quote(incident_id, safe='')}"
