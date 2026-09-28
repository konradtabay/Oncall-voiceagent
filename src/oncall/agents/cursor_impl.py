"""Cursor cloud agents."""

from __future__ import annotations

from collections.abc import Iterator

from oncall.incident.bridge import Bridge
from oncall.incident.cursor_client import CursorClient, HttpCursorClient
from oncall.incident.voice import voice_compact


class CursorImplementer:
    def __init__(self, client: CursorClient) -> None:
        self._client = client

    def create_agent_with_run(
        self, repo_url: str, prompt: str, env: dict | None = None
    ) -> tuple[str, str | None]:
        return self._client.create_agent_with_run(repo_url, prompt, env)

    def create_run(self, agent_id: str, text: str) -> str:
        return self._client.create_run(agent_id, text)

    def stream(self, agent_id: str, run_id: str) -> Iterator[str]:
        yield from self._client.stream(agent_id, run_id)

    def run_fix(self, agent_id: str, instructions: str, verify_target: str) -> str:
        run_id = self.create_run(agent_id, instructions)
        bridge = Bridge()
        parts: list[str] = []
        for chunk in bridge.consume(self.stream(agent_id, run_id)):
            parts.append(chunk)
        line = voice_compact("".join(parts))
        if line:
            return line
        return "Fix finished. Check the service when you can."


def cursor_from_settings(api_key: str, **kwargs: object) -> CursorImplementer:
    return CursorImplementer(
        HttpCursorClient(
            api_key,
            busy_wait=float(kwargs.get("busy_wait", 5.0)),
            max_busy_retries=int(kwargs.get("max_busy_retries", 25)),
        )
    )
