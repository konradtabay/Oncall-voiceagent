"""Telephony track tests — fakes only, no network."""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import FastAPI
from fastapi.testclient import TestClient

from oncall.seam import Answered, CallEnded, Dial, Hangup, Missed, SmsIn, SmsOut
from oncall.telephony import (
    Telephony,
    bind,
    reject_bad_signature,
    router,
    signature_ok,
)
from oncall.telephony.service import HANGUP_TWIML


@dataclass
class FakeTwilio:
    calls: list[dict] = field(default_factory=list)
    hangups: list[str] = field(default_factory=list)
    sms: list[dict] = field(default_factory=list)
    next_sid: str = "CA0001"

    def create_call(self, to: str, from_: str, voice_url: str, status_url: str) -> str:
        self.calls.append(
            {
                "to": to,
                "from_": from_,
                "voice_url": voice_url,
                "status_url": status_url,
            }
        )
        sid = self.next_sid
        self.next_sid = f"CA{int(sid[2:]) + 1:04d}"
        return sid

    def hangup(self, call_sid: str) -> None:
        self.hangups.append(call_sid)

    def send_sms(self, to: str, from_: str, body: str) -> None:
        self.sms.append({"to": to, "from_": from_, "body": body})

    def redirect_call(self, call_sid: str, url: str) -> None:
        pass


@dataclass
class FakeElevenLabs:
    registrations: list[dict] = field(default_factory=list)
    twiml: str = "<Response><Connect/></Response>"

    def register_call(
        self,
        incident_id: str,
        from_number: str,
        to_number: str,
    ) -> str:
        self.registrations.append(
            {
                "incident_id": incident_id,
                "from_number": from_number,
                "to_number": to_number,
            }
        )
        return self.twiml


def _make(
    twilio: FakeTwilio | None = None,
    eleven: FakeElevenLabs | None = None,
    events: list | None = None,
    sms_reply: str | None = "ack",
) -> tuple[Telephony, FakeTwilio, FakeElevenLabs, list]:
    twilio = twilio or FakeTwilio()
    eleven = eleven or FakeElevenLabs()
    events = events if events is not None else []

    def on_event(event):
        events.append(event)
        if isinstance(event, SmsIn):
            return sms_reply
        return None

    tel = Telephony(
        twilio,
        eleven,
        validator=None,
        on_event=on_event,
        from_number="+15550001111",
        voice_url="https://example.com/twilio/voice",
        status_url="https://example.com/twilio/status",
    )
    return tel, twilio, eleven, events


def test_human_answer_emits_answered_and_registers():
    tel, twilio, eleven, events = _make()
    sid = tel.dial(Dial("inc-1", "+15555550100"))

    response = tel.handle_voice(
        {
            "CallSid": sid,
            "AnsweredBy": "human",
            "CallStatus": "in-progress",
            "From": "+15550001111",
            "To": "+15555550100",
        },
        signature_ok=True,
    )

    assert response.body.decode() == eleven.twiml
    assert len(eleven.registrations) == 1
    assert eleven.registrations[0]["incident_id"] == "inc-1"
    assert events == [Answered("inc-1", sid)]
    assert len(twilio.calls) == 1


def test_machine_start_emits_missed_and_hangup_twiml():
    tel, _twilio, eleven, events = _make()
    sid = tel.dial(Dial("inc-1", "+15555550100"))

    response = tel.handle_voice(
        {
            "CallSid": sid,
            "AnsweredBy": "machine_start",
            "CallStatus": "in-progress",
            "From": "+15550001111",
            "To": "+15555550100",
        },
        signature_ok=True,
    )

    assert response.body.decode() == HANGUP_TWIML
    assert eleven.registrations == []
    assert events == [Missed("inc-1", "machine")]


def test_status_miss_reasons():
    for reason in ("no-answer", "busy", "failed", "canceled"):
        tel, _twilio, _eleven, events = _make()
        sid = tel.dial(Dial("inc-1", "+15555550100"))
        tel.handle_status(
            {"CallSid": sid, "CallStatus": reason},
            signature_ok=True,
        )
        assert events == [Missed("inc-1", reason)]


def test_status_completed_emits_call_ended():
    tel, _twilio, _eleven, events = _make()
    sid = tel.dial(Dial("inc-1", "+15555550100"))
    tel.handle_status(
        {"CallSid": sid, "CallStatus": "completed"},
        signature_ok=True,
    )
    assert events == [CallEnded(incident_id="inc-1")]


def test_reject_bad_signature_returns_403():
    response = reject_bad_signature()
    assert response.status_code == 403


def test_twilio_signature_with_query_param_in_url_only():
    from twilio.request_validator import RequestValidator

    token = "test-auth-token"
    bind(_make()[0], auth_token=token, public_base_url="https://example.ngrok.app")
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    params = {
        "CallSid": "CA123",
        "CallStatus": "ringing",
        "AnsweredBy": "human",
    }
    url = "https://example.ngrok.app/twilio/voice?incident_id=inc-1"
    signature = RequestValidator(token).compute_signature(url, params)
    response = client.post(
        "/twilio/voice?incident_id=inc-1",
        data=params,
        headers={"X-Twilio-Signature": signature},
    )
    assert response.status_code != 403


def test_bad_signature_path_via_router_returns_403():
    tel, *_ = _make()
    bind(tel, auth_token="test-auth-token")
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/twilio/voice",
        data={"CallSid": "CA999", "CallStatus": "ringing"},
        headers={"X-Twilio-Signature": "invalid"},
    )
    assert response.status_code == 403


def test_signature_ok_without_token_allows():
    assert signature_ok("https://example.com/", {}, "", None) is True
    assert signature_ok("https://example.com/", {}, "", "") is True


def test_sms_out_does_not_call_hangup():
    tel, twilio, _eleven, _events = _make()
    tel.dial(Dial("inc-1", "+15555550100"))
    tel.sms_out(SmsOut("inc-1", "hello", "text_turn"))
    assert len(twilio.sms) == 1
    assert twilio.sms[0]["body"] == "hello"
    assert twilio.hangups == []


def test_hangup_close_calls_hangup_once():
    tel, twilio, _eleven, _events = _make()
    sid = tel.dial(Dial("inc-1", "+15555550100"))
    tel.hangup(Hangup("inc-1", "close"))
    assert twilio.hangups == [sid]


def test_inbound_voice_unknown_sid_hangup_no_register():
    tel, _twilio, eleven, events = _make()
    response = tel.handle_voice(
        {
            "CallSid": "CAunknown",
            "AnsweredBy": "human",
            "CallStatus": "in-progress",
            "From": "+15555550999",
            "To": "+15550001111",
        },
        signature_ok=True,
    )
    assert response.body.decode() == HANGUP_TWIML
    assert eleven.registrations == []
    assert events == []


def test_handle_sms_passes_sms_in_and_returns_reply():
    tel, _twilio, _eleven, events = _make(sms_reply="got it")
    reply = tel.handle_sms(
        {"From": "+15555550100", "Body": "send the error log"},
        signature_ok=True,
    )
    assert reply == "got it"
    assert events == [SmsIn("+15555550100", "send the error log")]


def test_handle_voice_bad_signature_raises():
    tel, *_ = _make()
    try:
        tel.handle_voice({"CallSid": "CA1"}, signature_ok=False)
        assert False, "expected BadSignature"
    except Exception as exc:
        from oncall.telephony import BadSignature

        assert isinstance(exc, BadSignature)
