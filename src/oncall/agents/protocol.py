"""Protocol for diagnosis (stream) and fix (one spoken sentence)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol


class Implementer(Protocol):
    def create_agent_with_run(
        self, repo_url: str, prompt: str, env: dict | None = None
    ) -> tuple[str, str | None]:
        """Start a session; optional initial run id for the first stream."""

    def create_run(self, agent_id: str, text: str) -> str:
        ...

    def stream(self, agent_id: str, run_id: str) -> Iterator[str]:
        ...

    def run_fix(self, agent_id: str, instructions: str, verify_target: str) -> str:
        """Return one sentence to speak on the call after execute."""
