"""State machine tests for Track B — no network."""

from __future__ import annotations

from pathlib import Path

from oncall.incident import Machine, Store, Incident, start_receipt, closing_receipt
from oncall.seam import Dial, Hangup, SmsOut


def _store(tmp_path: Path) -> Store:
    return Store(str(tmp_path / "incidents.db"))


def _incident(
    incident_id: str = "inc-1",
    state: str = "diagnosing",
    to_number: str = "+15555550100",
    brief: str = "API is down",
    fix: str = "restart the api process",
) -> Incident:
    return Incident(
        id=incident_id,
        state=state,
        to_number=to_number,
        summary="API health check failed",
        logs="connection refused",
        verify_target="https://api.example/health",
        brief=brief,
        fix=fix,
    )


def _bring_to_in_call(machine: Machine, incident: Incident) -> Incident:
    machine.open_or_queue(incident)
    machine.ready_to_dial(incident.id, incident.brief, incident.fix)
    machine.on_answered(incident.id, "CA123")
    return machine.store.get(incident.id)


def test_execute_then_talking_does_not_emit_start_receipt(tmp_path: Path):
    store = _store(tmp_path)
    machine = Machine(store)
    incident = _bring_to_in_call(machine, _incident())

    cmds = machine.on_phase(incident.id, "execute")
    assert cmds == []
    loaded = store.get(incident.id)
    assert loaded.armed is True

    cmds = machine.on_phase(incident.id, "talking")
    assert cmds == []
    loaded = store.get(incident.id)
    assert loaded.armed is False
    assert not any(isinstance(c, SmsOut) and c.kind == "start_receipt" for c in cmds)


def test_execute_twice_emits_one_start_receipt_no_hangup(tmp_path: Path):
    store = _store(tmp_path)
    machine = Machine(store)
    incident = _bring_to_in_call(machine, _incident())

    assert machine.on_phase(incident.id, "execute") == []
    cmds = machine.on_phase(
        incident.id,
        "execute",
        issue="API is down",
        solution="restart the api process",
    )

    receipts = [c for c in cmds if isinstance(c, SmsOut) and c.kind == "start_receipt"]
    hangups = [c for c in cmds if isinstance(c, Hangup)]
    assert len(receipts) == 1
    assert hangups == []
    assert "API is down" in receipts[0].body
    assert "restart the api process" in receipts[0].body

    loaded = store.get(incident.id)
    assert loaded.state == "in_call"
    assert loaded.armed is False
    assert loaded.fixing is True
    assert len(loaded.issues) == 1


def test_failed_from_in_call_stays_in_call_no_closing(tmp_path: Path):
    store = _store(tmp_path)
    machine = Machine(store)
    incident = _bring_to_in_call(machine, _incident())
    machine.on_phase(incident.id, "execute")
    machine.on_phase(incident.id, "execute", issue="down", solution="restart")

    cmds = machine.on_phase(
        incident.id, "failed", issue="still down", solution="roll back"
    )
    assert cmds == []
    loaded = store.get(incident.id)
    assert loaded.state == "in_call"
    assert loaded.armed is False
    assert loaded.fixing is False
    assert loaded.brief == "still down"
    assert loaded.fix == "roll back"
    assert not any(isinstance(c, SmsOut) and c.kind == "closing_receipt" for c in cmds)


def test_verified_hangup_close_and_closing_receipt(tmp_path: Path):
    store = _store(tmp_path)
    machine = Machine(store)
    incident = _bring_to_in_call(machine, _incident())
    machine.on_phase(incident.id, "execute")
    machine.on_phase(
        incident.id,
        "execute",
        issue="disk full",
        solution="clear /tmp",
    )
    machine.on_phase(incident.id, "execute")
    machine.on_phase(
        incident.id,
        "execute",
        issue="cache warm",
        solution="flush redis",
    )

    cmds = machine.on_phase(incident.id, "verified")
    hangups = [c for c in cmds if isinstance(c, Hangup)]
    receipts = [c for c in cmds if isinstance(c, SmsOut) and c.kind == "closing_receipt"]
    assert len(hangups) == 1
    assert hangups[0].reason == "close"
    assert len(receipts) == 1
    body = receipts[0].body.lower()
    assert "disk full" in body
    assert "clear /tmp" in body
    assert "cache warm" in body
    assert "flush redis" in body
    assert "succeeded" in body

    loaded = store.get(incident.id)
    assert loaded.state == "closed"
    assert loaded.armed is False
    assert loaded.fixing is False
    assert all(i["success"] for i in loaded.issues)


def test_on_missed_opens_text_session(tmp_path: Path):
    store = _store(tmp_path)
    machine = Machine(store)
    incident = _incident(brief="Payment webhook failing", fix="redeploy worker")
    machine.open_or_queue(incident)
    machine.ready_to_dial(incident.id, incident.brief, incident.fix)

    cmds = machine.on_missed(incident.id, "no-answer")
    hangups = [c for c in cmds if isinstance(c, Hangup)]
    sms = [c for c in cmds if isinstance(c, SmsOut)]
    assert hangups == [Hangup(incident.id, "miss")]
    assert len(sms) == 1
    assert sms[0].kind == "text_turn"
    assert "Payment webhook failing" in sms[0].body
    assert "redeploy worker" in sms[0].body

    loaded = store.get(incident.id)
    assert loaded.state == "text_session"


def test_accept_inbound_call_is_false(tmp_path: Path):
    machine = Machine(_store(tmp_path))
    assert machine.accept_inbound_call() is False


def test_start_receipt_does_not_set_text_session(tmp_path: Path):
    store = _store(tmp_path)
    machine = Machine(store)
    incident = _bring_to_in_call(machine, _incident())
    machine.on_phase(incident.id, "execute")
    machine.on_phase(incident.id, "execute", issue="x", solution="y")
    loaded = store.get(incident.id)
    assert loaded.state == "in_call"
    assert loaded.state != "text_session"


def test_on_sms_during_in_call_enqueues_follow_up(tmp_path: Path):
    store = _store(tmp_path)
    machine = Machine(store)
    incident = _bring_to_in_call(machine, _incident())
    machine.on_phase(incident.id, "execute")
    assert store.get(incident.id).armed is True

    classification, cmds = machine.on_sms(incident.id, "send the error log")
    assert classification == "follow_up"
    assert cmds == []
    loaded = store.get(incident.id)
    assert loaded.state == "in_call"
    assert loaded.armed is True
    assert store.pop_turn(incident.id) == "send the error log"


def test_second_incident_queued_then_promoted_after_verified(tmp_path: Path):
    store = _store(tmp_path)
    machine = Machine(store)
    first = _incident("inc-1")
    machine.open_or_queue(first)
    machine.ready_to_dial(first.id, first.brief, first.fix)
    machine.on_answered(first.id, "CA1")

    second = _incident("inc-2", brief="DB lag", fix="failover")
    cmds = machine.open_or_queue(second)
    assert cmds == []
    assert store.get("inc-2") is None
    assert store.active().id == "inc-1"

    machine.on_phase(first.id, "execute")
    machine.on_phase(first.id, "execute", issue="a", solution="b")
    machine.on_phase(first.id, "verified")
    assert store.get("inc-1").state == "closed"
    assert store.active() is None

    promoted = machine.promote_queue()
    assert promoted is not None
    assert promoted.id == "inc-2"
    assert promoted.state == "diagnosing"
    assert store.active().id == "inc-2"


def test_phase_drop_from_in_call_no_closing_receipt(tmp_path: Path):
    store = _store(tmp_path)
    machine = Machine(store)
    incident = _bring_to_in_call(machine, _incident())
    machine.on_phase(incident.id, "execute")
    machine.on_phase(incident.id, "execute", issue="x", solution="y")

    cmds = machine.on_phase(incident.id, "drop")
    assert not any(isinstance(c, SmsOut) and c.kind == "closing_receipt" for c in cmds)
    hangups = [c for c in cmds if isinstance(c, Hangup)]
    assert hangups == [Hangup(incident.id, "drop")]
    assert store.get(incident.id).state == "dropped"


def test_second_alert_stays_queued_until_drop(tmp_path: Path):
    store = _store(tmp_path)
    machine = Machine(store)
    first = _incident("inc-1")
    machine.open_or_queue(first)
    machine.ready_to_dial(first.id, first.brief, first.fix)
    machine.on_answered(first.id, "CA1")

    second = _incident("inc-2")
    machine.open_or_queue(second)
    assert machine.promote_queue() is None

    machine.on_phase(first.id, "drop")
    assert store.get("inc-1").state == "dropped"
    assert store.active() is None

    promoted = machine.promote_queue()
    assert promoted is not None
    assert promoted.id == "inc-2"
    assert promoted.state == "diagnosing"


def test_receipt_helpers_are_plain_language():
    start = start_receipt("the worker crashed", "restart the worker")
    assert "the worker crashed" in start
    assert "restart the worker" in start
    assert "Traceback" not in start

    closing = closing_receipt(
        [
            {"issue": "disk full", "solution": "clear /tmp", "success": True},
            {"issue": "oom", "solution": "raise limit", "success": True},
        ]
    )
    assert "disk full" in closing
    assert "clear /tmp" in closing
    assert "oom" in closing
    assert "raise limit" in closing
    assert "succeeded" in closing.lower()


def test_ready_to_dial_returns_dial(tmp_path: Path):
    store = _store(tmp_path)
    machine = Machine(store)
    incident = _incident()
    machine.open_or_queue(incident)
    cmds = machine.ready_to_dial(incident.id, "brief text", "fix text")
    assert cmds == [Dial(incident.id, "+15555550100")]
    loaded = store.get(incident.id)
    assert loaded.state == "ringing"
    assert loaded.brief == "brief text"
    assert loaded.fix == "fix text"


def test_on_sms_text_session_is_turn(tmp_path: Path):
    store = _store(tmp_path)
    machine = Machine(store)
    incident = _incident()
    machine.open_or_queue(incident)
    machine.ready_to_dial(incident.id, incident.brief, incident.fix)
    machine.on_missed(incident.id, "busy")

    classification, cmds = machine.on_sms(incident.id, "try a different fix")
    assert classification == "turn"
    assert cmds == []
    assert store.pop_turn(incident.id) is None
    assert store.get(incident.id).state == "text_session"


def test_on_missed_when_already_text_session_noop(tmp_path: Path):
    store = _store(tmp_path)
    machine = Machine(store)
    incident = _incident()
    machine.open_or_queue(incident)
    machine.ready_to_dial(incident.id, incident.brief, incident.fix)
    machine.on_missed(incident.id, "no-answer")
    assert machine.on_missed(incident.id, "busy") == []
