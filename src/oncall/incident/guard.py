"""Refuse deploy-like tools until a Fix has started."""

from __future__ import annotations

DEPLOY_MARKERS = ("deploy", "ssh", "restart")


class DeployGuard:
    def __init__(self) -> None:
        self.fix_started = False
        self.armed = False

    def on_phase(self, value: str) -> None:
        if value == "execute":
            self.fix_started = True
            self.armed = False
        elif value == "talking":
            self.armed = False
        elif value == "failed":
            self.fix_started = False
            self.armed = False
        elif value == "verified":
            self.fix_started = False
            self.armed = False
        elif value == "drop":
            self.fix_started = False
            self.armed = False

    def note_phase(self, value: str) -> None:
        self.on_phase(value)

    def allow_tool(self, name: str) -> bool:
        if not any(marker in name.lower() for marker in DEPLOY_MARKERS):
            return True
        return self.fix_started

    def mark_fix_started(self) -> None:
        self.fix_started = True

    def mark_failed(self) -> None:
        self.fix_started = False
