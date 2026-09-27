"""Wiring: alert to dial, speech, receipts, and the queue. No network."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from oncall.app import create_app
from oncall.incident.cursor_client import CursorClient
from oncall.incident.machine import Machine
from oncall.incident.service import IncidentService
from oncall.incident.store import Store
from oncall.telephony.service import Telephony


def _sse(pairs: list[tuple[str, dict]]) -> list[str]:
    lines: list[str] = []
    for name, data in pairs:
        lines.append(f"event: {name}")
        lines.append("data: " + json.dumps(data))
        lines.append("")
    return lines


class ScriptCursor(CursorClient):
    def __init__(self) -> None:
        self.runs: list[str] = []

    def create_agent_with_run(
        self, repo_url: str, prompt: str, env: dict | None = None
    ) -> tuple[str, str | None]:
        self.runs.append(prompt)
        return "agent-1", "run-initial"

    def create_run(self, agent_id: str, text: str) -> str:
        self.runs.append(text)
        return f"run-{len(self.runs)}"

    def stream(self, agent_id: str, run_id: str):
        text = self.runs[-1] if run_id != "run-initial" else self.runs[0]
        if "End with a line" in text or "What broke:" in text:
            yield from _sse(
                [("assistant", {"text": "Worker died.\nFix: Restart it."})]
            )
            return
        if text == "no":
            yield from _sse(
                [
                    ("assistant", {"text": "Restarting it."}),
                    (
                        "tool_call",
                        {
                            "name": "phase",
                            "status": "completed",
                            "callId": "p2",
                            "args": {
                                "value": "execute",
                                "issue": "worker died",
                                "solution": "restart it",
                            },
                        },
                    ),
                ]
            )
            return
        if "Do this fix now" in text or text == "check":
            yield from _sse(
                [
                    ("assistant", {"text": "It is back."}),
                    (
                        "tool_call",
                        {
                            "name": "phase",
                            "status": "completed",
                            "callId": "p3",
                            "args": {"value": "verified"},
                        },
                    ),
                ]
            )
            return
        yield from _sse(
            [
                ("assistant", {"text": "Anything else?"}),
                (
                    "tool_call",
                    {
                        "name": "phase",
                        "status": "completed",
                        "callId": "p1",
                        "args": {"value": "execute"},
                    },
                ),
            ]
        )


class FakeTwilio:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.hungup: list[str] = []
        self.sms: list[str] = []
        self.redirects: list[dict] = []
        self._n = 0

    def create_call(self, to: str, from_: str, voice_url: str, status_url: str) -> str:
        self._n += 1
        sid = f"CA{self._n}"
        self.calls.append(sid)
        return sid

    def hangup(self, call_sid: str) -> None:
        self.hungup.append(call_sid)

    def send_sms(self, to: str, from_: str, body: str) -> None:
        self.sms.append(body)

    def redirect_call(self, call_sid: str, url: str) -> None:
        self.redirects.append({"sid": call_sid, "url": url})


class FakeEleven:
    def register_call(self, incident_id: str, from_number: str, to_number: str) -> str:
        return "<Response><Connect/></Response>"


def _world(tmp_path):
    store = Store(str(tmp_path / "inc.sqlite3"))
    machine = Machine(store)
    twilio = FakeTwilio()
    box: dict = {}

    def on_event(event):
        return box["service"].handle_event(event)

    telephony = Telephony(
        twilio,
        FakeEleven(),
        None,
        on_event,
        from_number="+15550001111",
        voice_url="https://example.test/twilio/voice",
        status_url="https://example.test/twilio/status",
    )
    service = IncidentService(
        store, machine, ScriptCursor(), telephony, repo_url="https://example.test/repo"
    )
    box["service"] = service
    app = create_app(service)
    return service, twilio, telephony, TestClient(app)


def test_voice_update_ignores_still_working(tmp_path):
    service, *_ = _world(tmp_path)
    service.publish_voice_update("inc-1", "Still working.")
    service.publish_voice_update("inc-1", "The worker is back.")
    assert service.wait_voice_update("inc-1", timeout=0.2) == "The worker is back."


def test_alert_dials_after_diagnosis(tmp_path):
    service, twilio, _telephony, client = _world(tmp_path)
    response = client.post(
        "/alerts",
        json={
            "summary": "worker down",
            "logs": "exit 1",
            "verify_target": "http://health",
            "to_number": "+15555550100",
            "incident_id": "inc-1",
        },
    )
    assert response.status_code == 200
    assert response.json()["state"] == "ringing"
    assert twilio.calls == ["CA1"]
    incident = service.store.get("inc-1")
    assert incident is not None
    assert incident.brief == "Worker died."
    assert incident.fix == "Restart it."
    assert incident.agent_id == "agent-1"


def test_call_stays_up_until_verified_then_receipts(tmp_path):
    service, twilio, telephony, client = _world(tmp_path)
    service._cursor_async = False
    client.post(
        "/alerts",
        json={
            "summary": "worker down",
            "logs": "exit 1",
            "verify_target": "http://health",
            "to_number": "+15555550100",
            "incident_id": "inc-1",
        },
    )
    voice = telephony.handle_voice(
        {"CallSid": "CA1", "AnsweredBy": "human", "From": "+15550001111", "To": "+15555550100"},
        True,
    )
    assert "Connect" in voice.body.decode()
    assert service.store.get("inc-1").state == "in_call"

    first = client.post(
        "/v1/chat/completions",
        json={"messages": []},
    )
    assert first.status_code == 200
    body = first.text
    assert "Worker died." in body
    assert "let me know" in body.lower()
    assert twilio.hungup == []
    assert twilio.sms == []
    assert service.store.get("inc-1").armed is False

    client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "yes"}]},
    )
    assert any("worker died" in message.lower() for message in twilio.sms)
    assert twilio.hungup == ["CA1"]
    closing = twilio.sms[-1]
    assert "succeeded" in closing.lower()
    assert service.store.get("inc-1").state == "closed"


def test_elevenlabs_phase_execute_once_starts_fix(tmp_path):
    service, twilio, telephony, client = _world(tmp_path)
    service._cursor_async = False
    client.post(
        "/alerts",
        json={
            "summary": "worker down",
            "logs": "exit 1",
            "verify_target": "http://health",
            "to_number": "+15555550100",
            "incident_id": "inc-1",
        },
    )
    telephony.handle_voice(
        {"CallSid": "CA1", "AnsweredBy": "human", "From": "+15550001111", "To": "+15555550100"},
        True,
    )
    diagnose_runs = len(service.cursor.runs)
    response = client.post(
        "/elevenlabs/phase", json={"value": "execute", "incident_id": "inc-1"}
    )
    assert response.status_code == 200
    assert "i'll keep you updated" in response.json()["result"].lower()
    assert len(service.cursor.runs) == diagnose_runs + 1
    assert any("worker died" in message.lower() for message in twilio.sms)
    assert twilio.hungup == ["CA1"]
    assert service.store.get("inc-1").state == "closed"


def test_miss_opens_text_session_and_callback_is_rejected(tmp_path):
    service, twilio, telephony, client = _world(tmp_path)
    client.post(
        "/alerts",
        json={
            "summary": "worker down",
            "logs": "exit 1",
            "verify_target": "http://health",
            "to_number": "+15555550100",
            "incident_id": "inc-1",
        },
    )
    telephony.handle_status({"CallSid": "CA1", "CallStatus": "no-answer"}, True)
    incident = service.store.get("inc-1")
    assert incident.state == "text_session"
    assert any("Worker died." in message for message in twilio.sms)
    rejected = telephony.handle_voice({"CallSid": "CAinbound", "CallStatus": "ringing"}, True)
    assert "Hangup" in rejected.body.decode()
    assert service.machine.accept_inbound_call() is False


def test_second_alert_waits_until_drop(tmp_path):
    _service, twilio, telephony, client = _world(tmp_path)
    client.post(
        "/alerts",
        json={
            "summary": "first",
            "logs": "",
            "verify_target": "http://a",
            "to_number": "+15555550100",
            "incident_id": "inc-1",
        },
    )
    telephony.handle_voice(
        {"CallSid": "CA1", "AnsweredBy": "human"},
        True,
    )
    queued = client.post(
        "/alerts",
        json={
            "summary": "second",
            "logs": "",
            "verify_target": "http://b",
            "to_number": "+15555550100",
            "incident_id": "inc-2",
        },
    )
    assert queued.json()["state"] == "queued"
    assert twilio.calls == ["CA1"]
    commands = _service.machine.on_phase("inc-1", "drop")
    assert not any(getattr(command, "kind", "") == "closing_receipt" for command in commands)
    _service._apply(commands)
    _service._promote()
    assert twilio.calls == ["CA1", "CA2"]
    assert _service.store.get("inc-2").state == "ringing"
