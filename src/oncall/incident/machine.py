"""Pure incident state machine. Emits seam Commands; persists via Store."""

from __future__ import annotations

from typing import Optional

from oncall.incident.models import Incident, QueuedAlert
from oncall.incident.receipts import closing_receipt, start_receipt, text_open
from oncall.incident.store import Store
from oncall.seam import Command, Dial, Hangup, SmsOut


class Machine:
    def __init__(self, store: Store) -> None:
        self.store = store

    def open_or_queue(self, incident: Incident) -> list[Command]:
        active = self.store.active()
        if active is not None and active.id != incident.id:
            self.store.enqueue(
                QueuedAlert(
                    id=incident.id,
                    summary=incident.summary,
                    logs=incident.logs,
                    verify_target=incident.verify_target,
                    to_number=incident.to_number,
                    created_order=0,
                )
            )
            return []
        incident.state = "diagnosing"
        self.store.save(incident)
        return []

    def ready_to_dial(
        self, incident_id: str, brief: str, fix: str
    ) -> list[Command]:
        incident = self._require(incident_id)
        incident.brief = brief
        incident.fix = fix
        incident.state = "ringing"
        self.store.save(incident)
        return [Dial(incident_id, incident.to_number)]

    def on_answered(self, incident_id: str, call_sid: str) -> list[Command]:
        incident = self._require(incident_id)
        incident.state = "in_call"
        incident.call_sid = call_sid
        self.store.save(incident)
        return []

    def on_missed(self, incident_id: str, reason: str) -> list[Command]:
        incident = self._require(incident_id)
        if incident.state == "text_session":
            return []
        if incident.state != "ringing":
            return []
        incident.state = "text_session"
        self.store.save(incident)
        return [
            Hangup(incident_id, "miss"),
            SmsOut(
                incident_id,
                text_open(incident.brief, incident.fix),
                "text_turn",
            ),
        ]

    def on_phase(
        self,
        incident_id: str,
        phase: str,
        issue: str = "",
        solution: str = "",
    ) -> list[Command]:
        incident = self._require(incident_id)
        commands: list[Command] = []

        if phase == "talking":
            if incident.armed:
                incident.armed = False
            self.store.save(incident)
            return []

        if phase == "execute":
            if not incident.armed:
                incident.armed = True
                self.store.save(incident)
                return []
            incident.armed = False
            incident.fixing = True
            recorded_issue = issue or incident.fix
            recorded_solution = solution or incident.fix
            incident.issues.append(
                {
                    "issue": recorded_issue,
                    "solution": recorded_solution,
                    "success": False,
                }
            )
            self.store.save(incident)
            return [
                SmsOut(
                    incident_id,
                    start_receipt(recorded_issue, recorded_solution),
                    "start_receipt",
                )
            ]

        if phase == "verified":
            for item in incident.issues:
                item["success"] = True
            if incident.state == "in_call":
                commands.append(Hangup(incident_id, "close"))
            commands.append(
                SmsOut(
                    incident_id,
                    closing_receipt(incident.issues),
                    "closing_receipt",
                )
            )
            incident.state = "closed"
            incident.fixing = False
            incident.armed = False
            self.store.save(incident)
            return commands

        if phase == "failed":
            incident.armed = False
            incident.fixing = False
            if issue:
                incident.brief = issue
            if solution:
                incident.fix = solution
            self.store.save(incident)
            return []

        if phase == "drop":
            prior = incident.state
            incident.state = "dropped"
            incident.armed = False
            incident.fixing = False
            if prior in ("in_call", "ringing"):
                commands.append(Hangup(incident_id, "drop"))
            elif prior == "text_session" and incident.call_sid:
                commands.append(Hangup(incident_id, "drop"))
            self.store.save(incident)
            return commands

        return []

    def on_sms(
        self, incident_id: str, body: str
    ) -> tuple[str, list[Command]]:
        incident = self._require(incident_id)
        if incident.state == "text_session":
            return ("turn", [])
        self.store.enqueue_turn(incident_id, body)
        return ("follow_up", [])

    def accept_inbound_call(self) -> bool:
        return False

    def promote_queue(self) -> Optional[Incident]:
        if self.store.active() is not None:
            return None
        alert = self.store.pop_next()
        if alert is None:
            return None
        incident = Incident(
            id=alert.id,
            state="diagnosing",
            to_number=alert.to_number,
            summary=alert.summary,
            logs=alert.logs,
            verify_target=alert.verify_target,
            brief="",
            fix="",
        )
        self.store.save(incident)
        return incident

    def _require(self, incident_id: str) -> Incident:
        incident = self.store.get(incident_id)
        if incident is None:
            raise KeyError(f"unknown incident: {incident_id}")
        return incident
