"""Port protocols for Twilio and ElevenLabs."""

from __future__ import annotations

from typing import Protocol


class TwilioPort(Protocol):
    def create_call(
        self,
        to: str,
        from_: str,
        voice_url: str,
        status_url: str,
    ) -> str:
        """Create an outbound call; return the CallSid.

        Real adapters must enable answering-machine detection
        (Twilio ``MachineDetection=Enable``).
        """
        ...

    def hangup(self, call_sid: str) -> None:
        """End an in-progress call."""
        ...

    def send_sms(self, to: str, from_: str, body: str) -> None:
        """Send an outbound SMS."""
        ...


class ElevenLabsPort(Protocol):
    def register_call(
        self,
        incident_id: str,
        from_number: str,
        to_number: str,
    ) -> str:
        """Register the call with ElevenLabs and return TwiML."""
        ...
