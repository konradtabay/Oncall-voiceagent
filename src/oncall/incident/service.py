"""Connect the incident machine, the coding agent, and telephony."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid
from collections.abc import Iterator
from typing import Any

import httpx

from oncall.agents.protocol import Implementer
from oncall.incident.bridge import Bridge
from oncall.incident.guard import DeployGuard
from oncall.incident.machine import Machine
from oncall.incident.models import Incident
from oncall.incident.prompts import AGENT_PROMPT, DIAGNOSE_INSTRUCTION
from oncall.incident.store import Store
from oncall.incident.transcripts import fetch_conversation, format_transcript_text
from oncall.incident.voice import (
    KEEP_UPDATED,
    call_opening,
    split_diagnosis,
    voice_compact,
)
from oncall.seam import (
    Answered,
    CallEnded,
    Command,
    Dial,
    Hangup,
    Missed,
    SmsIn,
    SmsOut,
)
from oncall.telephony.service import Telephony

log = logging.getLogger(__name__)


def opening_line(incident: Incident) -> str:
    return call_opening(incident.brief or incident.summary, incident.fix)


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


class IncidentService:
    def __init__(
        self,
        store: Store,
        machine: Machine,
        implementer: Implementer,
        telephony: Telephony,
        *,
        repo_url: str,
        elevenlabs_api_key: str = "",
        diagnose_timeout_secs: float = 90.0,
    ) -> None:
        self.store = store
        self.machine = machine
        self.implementer = implementer
        self.telephony = telephony
        self.repo_url = repo_url
        self._elevenlabs_api_key = elevenlabs_api_key
        self._diagnose_timeout_secs = diagnose_timeout_secs
        self._guards: dict[str, DeployGuard] = {}
        self._opened: set[str] = set()
        self._voice_updates: dict[str, queue.Queue[str]] = {}
        self._update_waiters: dict[str, int] = {}
        self._hold_hangup: set[str] = set()
        self._update_lock = threading.Lock()
        self._fix_async = True
        self._fix_running: set[str] = set()
        self._spoken_ready: dict[str, str] = {}

    def call_context(self, incident_id: str) -> dict[str, str]:
        incident = self.store.get(incident_id)
        if incident is None:
            return {}
        opening = call_opening(
            incident.brief or incident.summary,
            incident.fix,
        )
        from oncall.incident.voice import voice_agent

        return {
            "brief": voice_agent(incident.brief or incident.summary),
            "fix": voice_agent(incident.fix),
            "project": "",
            "opening": opening,
        }

    def open_alert(
        self,
        *,
        summary: str,
        logs: str,
        verify_target: str,
        to_number: str,
        incident_id: str | None = None,
    ) -> Incident:
        if incident_id:
            existing = self.store.get(incident_id)
            if existing is not None and existing.state not in {"closed"}:
                return existing

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

    def handle_event(
        self, event: Answered | Missed | SmsIn | CallEnded
    ) -> str | None:
        if isinstance(event, Answered):
            self.machine.on_answered(
                event.incident_id,
                event.call_sid,
                event.conversation_id,
            )
            return None
        if isinstance(event, CallEnded):
            self._fetch_transcript_async(event.incident_id)
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

        if _wants_execute(user):
            apply_phase("execute")
            self._start_fix(incident_id)
            yield KEEP_UPDATED
            return

    def on_voice_phase(
        self,
        value: str,
        issue: str = "",
        solution: str = "",
        incident_id: str = "",
    ) -> dict[str, str]:
        incident = self.store.get(incident_id) if incident_id else None
        if incident is None:
            incident = self.store.active()
        if incident is None:
            return {"result": "No open incident."}
        phase = (value or "").strip().lower()
        if phase not in {"talking", "execute", "verified", "failed", "drop"}:
            return {"result": "Unknown phase."}
        self.store.append_call_log(
            incident.id,
            "phase",
            json.dumps(
                {
                    "value": phase,
                    "issue": issue,
                    "solution": solution,
                }
            ),
        )
        guard = self._guards.setdefault(incident.id, DeployGuard())
        guard.on_phase(phase)
        phase_issue = issue or incident.brief or incident.summary
        phase_solution = solution or incident.fix
        self._apply(
            self.machine.on_phase(
                incident.id,
                phase,
                phase_issue,
                phase_solution,
            )
        )
        if phase in {"verified", "drop"}:
            self._promote()
        if phase == "execute":
            current = self.store.get(incident.id)
            if current is not None and current.fixing:
                self._start_fix(incident.id)
                return {
                    "result": (
                        "Fix started on the backend. You did the right thing. "
                        "Do not apologize or say you cannot run commands. "
                        f"Say exactly: {KEEP_UPDATED} "
                        "Then call the updates tool once and wait for the response. "
                        "When updates returns text, you must speak that text out loud "
                        "immediately — that is the fix result. Do not skip_turn. "
                        "If it returns nothing yet, call updates again and say nothing. "
                        "If they ask you something, answer them, then call updates again. "
                        "Do not fill silence. Do not say you are still working."
                    )
                }
            return {"result": "Fix is already running or could not start."}
        if phase == "verified":
            return {"result": "Tell them it succeeded. They will get a closing text."}
        if phase == "failed":
            return {"result": "Tell them the fix did not stick and what to try next."}
        if phase == "drop":
            return {
                "result": (
                    "Only use drop when they want to end the call. "
                    "Say a brief goodbye. The call should end."
                )
            }
        return {"result": "Keep talking. Do not start the fix."}

    def _fetch_transcript_async(self, incident_id: str) -> None:
        if not self._elevenlabs_api_key:
            return

        def job() -> None:
            for wait_secs in (4, 12, 25):
                time.sleep(wait_secs)
                incident = self.store.get(incident_id)
                if incident is None or not incident.conversation_id:
                    return
                try:
                    detail = fetch_conversation(
                        self._elevenlabs_api_key,
                        incident.conversation_id,
                    )
                    if detail.get("status") == "processing":
                        continue
                    text = format_transcript_text(detail)
                    for row in self.store.list_call_logs(incident_id):
                        text += (
                            f"\n[{row['created_at']}] {row['kind']}: {row['body']}"
                        )
                    summary = ""
                    analysis = detail.get("analysis") or {}
                    if isinstance(analysis, dict):
                        summary = str(analysis.get("transcript_summary") or "")
                    self.store.save_call_transcript(
                        incident_id,
                        incident.conversation_id,
                        summary,
                        text.strip(),
                        json.dumps(detail.get("transcript") or []),
                    )
                    log.info(
                        "call transcript saved incident=%s conversation=%s summary=%s\n%s",
                        incident_id,
                        incident.conversation_id,
                        summary or "(none)",
                        text.strip(),
                    )
                    return
                except Exception:
                    continue

        threading.Thread(target=job, daemon=True).start()

    def transcript_for(self, incident_id: str) -> dict[str, str] | None:
        row = self.store.get_call_transcript(incident_id)
        if row is None:
            return None
        return {
            "incident_id": incident_id,
            "conversation_id": row["conversation_id"],
            "summary": row["summary"],
            "transcript": row["transcript_text"],
            "fetched_at": row["fetched_at"],
        }

    def publish_voice_update(self, incident_id: str, text: str, *, exact: bool = False) -> None:
        line = text.strip() if exact else _speakable(text)
        if not line:
            return
        with self._update_lock:
            self._spoken_ready[incident_id] = line
            self._voice_updates.setdefault(incident_id, queue.Queue()).put(line)
            if self._update_waiters.get(incident_id, 0) > 0:
                self._hold_hangup.add(incident_id)

    def ready_voice_update(self, incident_id: str) -> str:
        incident_id = self.resolve_voice_incident(incident_id)
        with self._update_lock:
            return self._spoken_ready.get(incident_id, "")

    def resolve_voice_incident(self, incident_id: str) -> str:
        raw = (incident_id or "").strip()
        if raw.lower() in {"", "unknown", "none", "null"}:
            raw = ""
        if raw and self.store.get(raw) is not None:
            return raw
        active = self.store.active()
        if active is not None:
            return active.id
        return raw

    def wait_voice_update(self, incident_id: str, timeout: float = 12) -> str:
        with self._update_lock:
            pending = self._voice_updates.setdefault(incident_id, queue.Queue())
            self._update_waiters[incident_id] = (
                self._update_waiters.get(incident_id, 0) + 1
            )
        try:
            return pending.get(timeout=timeout)
        except queue.Empty:
            return ""
        finally:
            with self._update_lock:
                self._update_waiters[incident_id] = max(
                    0, self._update_waiters.get(incident_id, 1) - 1
                )

    def _start_fix(self, incident_id: str) -> None:
        if incident_id in self._fix_running:
            return
        self._fix_running.add(incident_id)

        def job() -> None:
            try:
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
                try:
                    parts = list(self._run(incident_id, ask))
                    line = voice_compact("".join(parts))
                    if not line:
                        line = self.implementer.run_fix(
                            incident.agent_id, ask, incident.verify_target
                        )
                    self.publish_voice_update(incident_id, line, exact=True)
                except Exception:
                    log.exception("fix failed incident=%s", incident_id)
                    self.publish_voice_update(
                        incident_id,
                        "The fix did not finish. You will get a text with next steps.",
                        exact=True,
                    )
            finally:
                self._fix_running.discard(incident_id)

        if self._fix_async:
            threading.Thread(target=job, daemon=True).start()
        else:
            job()

    def _diagnose_and_dial(self, incident: Incident) -> None:
        holder: list[tuple[str, str]] = []

        def work() -> None:
            try:
                holder.append(self._run_diagnosis(incident))
            except Exception:
                log.exception("diagnose failed incident=%s", incident.id)
                fallback = incident.logs or incident.summary or "See alert logs."
                holder.append((incident.summary, fallback))

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        thread.join(timeout=self._diagnose_timeout_secs)
        if not holder:
            brief = incident.summary
            fix = incident.logs or "Inspect logs and restart the service."
            self._apply(self.machine.ready_to_dial(incident.id, brief, fix))
            return
        brief, fix = holder[0]
        self._apply(self.machine.ready_to_dial(incident.id, brief, fix))

    def _run_diagnosis(self, incident: Incident) -> tuple[str, str]:
        ask = (
            f"{DIAGNOSE_INSTRUCTION}\n"
            f"What broke: {incident.summary}\n"
            f"Logs: {incident.logs}\n"
            f"Verify target: {incident.verify_target}\n"
            "Use the two-line Brief: / Fix: format from your instructions."
        )
        prompt = f"{AGENT_PROMPT}\n{ask}"
        agent_id, initial_run_id = self.implementer.create_agent_with_run(
            self.repo_url,
            prompt,
            {"verify_target": incident.verify_target},
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
        return split_diagnosis(text)

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
            yield from bridge.consume(
                self.implementer.stream(incident.agent_id, run_id)
            )
        finally:
            if manage_lock:
                self.store.set_run_lock(incident_id, False)
                self._drain(incident_id)

    def _create_run_with_backoff(self, agent_id: str, text: str) -> str:
        last_error: httpx.HTTPStatusError | None = None
        for attempt in range(8):
            try:
                return self.implementer.create_run(agent_id, text)
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

    def _apply(self, commands: list[Command], *, defer_hangup: bool = True) -> None:
        for command in commands:
            if (
                defer_hangup
                and isinstance(command, Hangup)
                and command.incident_id in self._hold_hangup
            ):
                self._hold_hangup.discard(command.incident_id)
                threading.Timer(
                    15.0,
                    lambda hung=command: self._apply([hung], defer_hangup=False),
                ).start()
                continue
            if isinstance(command, Dial):
                self.telephony.dial(command)
            elif isinstance(command, Hangup):
                self.telephony.hangup(command)
            elif isinstance(command, SmsOut):
                self.telephony.sms_out(command)


def _speakable(text: str) -> str:
    line = voice_compact(text)
    if not line or line.lower().rstrip(".") == "still working":
        return ""
    return line


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
