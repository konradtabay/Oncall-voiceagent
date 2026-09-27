"""Incident and queue models for the on-call voice service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

IncidentState = Literal[
    "diagnosing",
    "ringing",
    "in_call",
    "text_session",
    "closed",
    "dropped",
    "queued",
]


@dataclass
class Incident:
    id: str
    state: str
    to_number: str
    summary: str
    logs: str
    verify_target: str
    brief: str
    fix: str
    armed: bool = False
    fixing: bool = False
    agent_id: str = ""
    call_sid: str = ""
    conversation_id: str = ""
    run_locked: bool = False
    issues: list = field(default_factory=list)


@dataclass
class QueuedAlert:
    id: str
    summary: str
    logs: str
    verify_target: str
    to_number: str
    created_order: int
