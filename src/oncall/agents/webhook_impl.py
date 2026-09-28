"""HTTP webhook for any coding agent (Claude, Codex, custom)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Any

import httpx

from oncall.incident.voice import voice_compact


class WebhookImplementer:
    def __init__(self, webhook_url: str, *, client: httpx.Client | None = None) -> None:
        self._url = webhook_url.rstrip("/")
        self._owns = client is None
        self._client = client or httpx.Client(timeout=httpx.Timeout(600.0, connect=30.0))
        self._pending: dict[str, str] = {}
        self._repos: dict[str, str] = {}
        self._verify: dict[str, str] = {}
        self._run_prompts: dict[tuple[str, str], str] = {}

    def close(self) -> None:
        if self._owns:
            self._client.close()

    def _post(
        self,
        repo_url: str,
        instructions: str,
        verify_target: str,
    ) -> tuple[str, bool]:
        response = self._client.post(
            self._url,
            json={
                "repo_url": repo_url,
                "instructions": instructions,
                "verify_target": verify_target,
            },
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        text = str(data.get("text") or "").strip()
        ok = bool(data.get("ok", True))
        return text, ok

    def create_agent_with_run(
        self, repo_url: str, prompt: str, env: dict | None = None
    ) -> tuple[str, str | None]:
        agent_id = uuid.uuid4().hex
        verify = ""
        if env and isinstance(env.get("verify_target"), str):
            verify = env["verify_target"]
        text, ok = self._post(repo_url, prompt, verify)
        if not ok or not text:
            text = text or "Could not diagnose from the alert."
        self._repos[agent_id] = repo_url
        self._verify[agent_id] = verify
        self._pending[agent_id] = text
        return agent_id, "run-initial"

    def create_run(self, agent_id: str, text: str) -> str:
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        self._run_prompts[(agent_id, run_id)] = text
        return run_id

    def stream(self, agent_id: str, run_id: str) -> Iterator[str]:
        if run_id == "run-initial" and agent_id in self._pending:
            body = self._pending.pop(agent_id)
            yield from self._yield_sse(body)
            return
        repo = self._repos.get(agent_id, "")
        verify = self._verify.get(agent_id, "")
        prompt = self._run_prompts.get((agent_id, run_id), "")
        body, _ok = self._post(repo, prompt, verify)
        yield from self._yield_sse(body)

    def run_fix(self, agent_id: str, instructions: str, verify_target: str) -> str:
        repo = self._repos.get(agent_id, "")
        text, ok = self._post(repo, instructions, verify_target)
        if not ok:
            return text or "The fix did not complete."
        line = voice_compact(text)
        return line or text or "Fix finished."

    @staticmethod
    def _yield_sse(text: str) -> Iterator[str]:
        payload = {"text": text}
        yield "\n".join(["event: assistant", "data: " + json.dumps(payload), ""])
