"""Commands and events shared by telephony and incident.

Telephony emits Answered, Missed, and SmsIn.
Incident emits Dial, Hangup, and SmsOut.
Utterance comes from the custom-LLM endpoint, not from Twilio.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

HangupReason = Literal["close", "miss", "drop"]
SmsKind = Literal["start_receipt", "closing_receipt", "text_turn", "follow_up"]
MissReason = Literal["no-answer", "busy", "failed", "canceled", "machine"]


@dataclass(frozen=True)
class Dial:
    incident_id: str
    to_number: str


@dataclass(frozen=True)
class Hangup:
    incident_id: str
    reason: HangupReason


@dataclass(frozen=True)
class SmsOut:
    incident_id: str
    body: str
    kind: SmsKind


@dataclass(frozen=True)
class Answered:
    incident_id: str
    call_sid: str


@dataclass(frozen=True)
class Missed:
    incident_id: str
    reason: MissReason


@dataclass(frozen=True)
class SmsIn:
    from_number: str
    body: str


@dataclass(frozen=True)
class Utterance:
    incident_id: str
    text: str


Command = Union[Dial, Hangup, SmsOut]
Event = Union[Answered, Missed, SmsIn, Utterance]
