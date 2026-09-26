"""Connect the incident machine, the Cursor bridge, and telephony."""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Iterator
from typing import Any

import httpx

from oncall.incident.bridge import Bridge
from oncall.incident.cursor_client import CursorClient
from oncall.incident.guard import DeployGuard
from oncall.incident.machine import Machine
from oncall.incident.models import Incident
from oncall.incident.prompts import AGENT_PROMPT, DIAGNOSE_INSTRUCTION
from oncall.incident.store import Store
from oncall.seam import Answered, Command, Dial, Hangup, Missed, SmsIn, SmsOut
from oncall.telephony.service import Telephony


def split_diagnosis(text: str) -> tuple[str, str]:
    cleaned = text.replace("Still working.", "").strip()
    if "Fix:" in cleaned:
        brief, fix = cleaned.split("Fix:", 1)
        return brief.strip(), fix.strip()
    return cleaned, cleaned


def _plain_speech(text: str) -> str:
    cleaned = text.replace("**", "").replace("*", "")
    while "\n\n" in cleaned:
        cleaned = cleaned.replace("\n\n", "\n")
    return cleaned.strip()


def opening_line(incident: Incident) -> str:
    brief = _plain_speech(incident.brief)
    fix = _plain_speech(incident.fix)
    return f"{brief} The fix is {fix}".strip()


def _wants_execute(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "execute",
            "go ahead",
            "do it",
            "run the fix",
            "run it",
            "yes",
        )
    )


def _nothing_else(text: str) -> bool:
    lowered = text.lower().strip()
    if lowered in {
        "no",
        "nope",
        "nothing",
        "nothing else",
        "that's all",
        "thats all",
        "go",
        "start",
    }:
        return True
    return "nothing else" in lowered


class IncidentService:
    def __init__(
        self,
        store: Store,
        machine: Machine,
        cursor: CursorClient,
        telephony: Telephony,
        *,
        repo_url: str,
    ) -> None:
        self.store = store
        self.machine = machine
        self.cursor = cursor
        self.telephony = telephony
        self.repo_url = repo_url
        self._guards: dict[str, DeployGuard] = {}
        self._opened: set[str] = set()
        self._cursor_async = True

    def open_alert(
        self,
        *,
        summary: str,
        logs: str,
        verify_target: str,
        to_number: str,
        incident_id: str | None = None,
    ) -> Incident:
        incident = Incident(
            id=incident_id or uuid.uuid4().hex,
            state="diagnosing",
            to_number=to_number,
            summary=summary,
            logs=logs,
            verify_target=verify_target,
            brief="",
            fix="",
        )
        self.machine.open_or_queue(incident)
        saved = self.store.get(incident.id)
        if saved is not None and saved.state == "diagnosing":
            self._diagnose_and_dial(saved)
            return self.store.get(incident.id) or saved
        incident.state = "queued"
        return incident

    def handle_event(self, event: Answered | Missed | SmsIn) -> str | None:
        if isinstance(event, Answered):
            self.machine.on_answered(event.incident_id, event.call_sid)
            return None
        if isinstance(event, Missed):
            self._apply(self.machine.on_missed(event.incident_id, event.reason))
            return None
        incident = self.store.latest_for_number(event.from_number)
        if incident is None:
            active = self.store.active()
            incident = active
        if incident is None:
            return None
        kind, commands = self.machine.on_sms(incident.id, event.body)
        self._apply(commands)
        if kind == "turn":
            if self.store.get(incident.id).run_locked:  # type: ignore[union-attr]
                return None
            spoken = "".join(self._run(incident.id, event.body))
            if spoken:
                self.telephony.sms_out(
                    SmsOut(incident.id, spoken, "text_turn")
                )
            return None
        current = self.store.get(incident.id)
        if current is not None and not current.run_locked:
            self._drain(incident.id)
        return None

    def completion(self, messages: list[dict[str, Any]]) -> Iterator[str]:
        incident = self.store.active()
        if incident is None:
            yield "There is no open incident."
            return
        user = _last_user(messages)
        if incident.id not in self._opened:
            self._opened.add(incident.id)
            yield opening_line(incident)
            yield " Anything else before I run the fix?"
            return
        if not user:
            return
        current = self.store.get(incident.id)
        if current is not None and current.run_locked:
            self.store.enqueue_turn(incident.id, user)
            yield "Still working."
            return
        handled_local = False
        for chunk in self._local_voice_turn(incident.id, user):
            handled_local = True
            yield chunk
        if handled_local:
            return
        try:
            yield from self._run(incident.id, user)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                yield (
                    "The engineering agent is rate limited. "
                    "Say execute, then no, to confirm without waiting."
                )
            else:
                yield (
                    "Still waking up the engineering agent. "
                    "Say that again in a few seconds."
                )
        except Exception:
            yield (
                "I cannot reach the engineering agent right now. "
                "Hang up and I will text you."
            )

    def _local_voice_turn(self, incident_id: str, user: str) -> Iterator[str]:
        """Handle confirm/execute on the call without Cursor (avoids follow-up rate limits)."""
        incident = self.store.get(incident_id)
        if incident is None or incident.state not in {"in_call", "text_session"}:
            return
        guard = self._guards.setdefault(incident_id, DeployGuard())

        def apply_phase(value: str) -> None:
            guard.on_phase(value)
            self._apply(
                self.machine.on_phase(
                    incident_id,
                    value,
                    incident.brief or incident.summary,
                    incident.fix,
                )
            )

        if not incident.armed and _wants_execute(user):
            apply_phase("execute")
            yield "Okay. Anything else before I start?"
            return

        incident = self.store.get(incident_id)
        if incident is not None and incident.armed and _nothing_else(user):
            apply_phase("execute")
            yield "Starting now. You will get a text receipt."
            return

    def on_voice_phase(
        self,
        value: str,
        issue: str = "",
        solution: str = "",
        incident_id: str = "",
    ) -> dict[str, str]:
        """ElevenLabs tool: conversation stays there; Cursor runs only after a confirmed fix."""
        incident = self.store.get(incident_id) if incident_id else None
        if incident is None:
            incident = self.store.active()
        if incident is None:
            return {"result": "No open incident."}
        phase = (value or "").strip().lower()
        if phase not in {"talking", "execute", "verified", "failed", "drop"}:
            return {"result": "Unknown phase."}
        was_armed = incident.armed
        guard = self._guards.setdefault(incident.id, DeployGuard())
        guard.on_phase(phase)
        self._apply(
            self.machine.on_phase(
                incident.id,
                phase,
                issue or incident.brief or incident.summary,
                solution or incident.fix,
            )
        )
        if phase in {"verified", "drop"}:
            self._promote()
        if phase == "execute" and not was_armed:
            return {
                "result": (
                    "Do not start the fix yet. Ask if there is anything else "
                    "to change. If they say no, call phase with value execute again."
                )
            }
        if phase == "execute" and was_armed:
            self._start_cursor_fix(incident.id)
            return {
                "result": (
                    "Tell them you are starting the fix and they should stay on the line. "
                    "A text receipt is on the way."
                )
            }
        if phase == "verified":
            return {"result": "Tell them it succeeded. They will get a closing text."}
        if phase == "failed":
            return {"result": "Tell them the fix did not stick and what to try next."}
        if phase == "drop":
            return {"result": "Say goodbye. The call should end."}
        return {"result": "Keep talking. Do not start the fix."}

    def _start_cursor_fix(self, incident_id: str) -> None:
        incident = self.store.get(incident_id)
        if incident is None or not incident.agent_id:
            return
        ask = (
            "The Maintainer confirmed the fix and said there is nothing else. "
            f"Do this fix now: {incident.fix}. "
            f"Issue: {incident.brief or incident.summary}. "
            f"Then check {incident.verify_target}. "
            "Call the phase tool with verified if it is back, or failed if it is not. "
            "Do not ask them to confirm again."
        )

        def job() -> None:
            try:
                "".join(self._run(incident_id, ask))
            except Exception:
                return

        if self._cursor_async:
            threading.Thread(target=job, daemon=True).start()
            return
        job()

    def _diagnose_and_dial(self, incident: Incident) -> None:
        ask = (
            f"{DIAGNOSE_INSTRUCTION}\n"
            f"What broke: {incident.summary}\n"
            f"Logs: {incident.logs}\n"
            f"Verify target: {incident.verify_target}\n"
            "End with a line starting Fix: "
        )
        prompt = f"{AGENT_PROMPT}\n{ask}"
        agent_id, initial_run_id = self.cursor.create_agent_with_run(
            self.repo_url, prompt, None
        )
        incident.agent_id = agent_id
        self.store.save(incident)
        text = "".join(
            self._run(
                incident.id,
                ask,
                run_id=initial_run_id,
                manage_lock=True,
            )
        )
        brief, fix = split_diagnosis(text)
        self._apply(self.machine.ready_to_dial(incident.id, brief, fix))

    def _run(
        self,
        incident_id: str,
        text: str,
        *,
        run_id: str | None = None,
        manage_lock: bool = True,
    ) -> Iterator[str]:
        incident = self.store.get(incident_id)
        if incident is None or not incident.agent_id:
            return
        guard = self._guards.setdefault(incident_id, DeployGuard())
        self.store.set_run_lock(incident_id, True)

        def on_phase(value: str, issue: str, solution: str) -> None:
            guard.on_phase(value)
            self._apply(self.machine.on_phase(incident_id, value, issue, solution))
            if value in {"verified", "drop"}:
                self._promote()

        bridge = Bridge(on_phase=on_phase)
        try:
            if run_id is None:
                run_id = self._create_run_with_backoff(incident.agent_id, text)
            yield from bridge.consume(self.cursor.stream(incident.agent_id, run_id))
        finally:
            if manage_lock:
                self.store.set_run_lock(incident_id, False)
                self._drain(incident_id)

    def _create_run_with_backoff(self, agent_id: str, text: str) -> str:
        last_error: httpx.HTTPStatusError | None = None
        for attempt in range(8):
            try:
                return self.cursor.create_run(agent_id, text)
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response.status_code != 429 or attempt >= 7:
                    raise
                time.sleep(min(60.0, 8.0 * (attempt + 1)))
        if last_error is not None:
            raise last_error
        raise RuntimeError("create_run failed")

    def _drain(self, incident_id: str) -> None:
        pending = self.store.pop_turn(incident_id)
        if pending is None:
            return
        spoken = "".join(self._run(incident_id, pending, manage_lock=True))
        if spoken:
            self.telephony.sms_out(SmsOut(incident_id, spoken, "follow_up"))

    def _promote(self) -> None:
        nxt = self.machine.promote_queue()
        if nxt is not None:
            self._diagnose_and_dial(nxt)

    def _apply(self, commands: list[Command]) -> None:
        for command in commands:
            if isinstance(command, Dial):
                self.telephony.dial(command)
            elif isinstance(command, Hangup):
                self.telephony.hangup(command)
            elif isinstance(command, SmsOut):
                self.telephony.sms_out(command)


def _last_user(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            content = message.get("content") or ""
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = [
                    str(part.get("text") or "")
                    for part in content
                    if isinstance(part, dict)
                ]
                return "".join(parts)
    return ""


def sse_bytes(chunks: Iterator[str]) -> Iterator[bytes]:
    for chunk in chunks:
        payload = {
            "choices": [{"index": 0, "delta": {"content": chunk}}],
        }
        yield f"data: {json.dumps(payload)}\n\n".encode()
    yield b"data: [DONE]\n\n"
