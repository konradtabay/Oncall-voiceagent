"""Cursor cloud agent HTTP client (protocol + httpx implementation)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import httpx

API_BASE = "https://api.cursor.com"


class CursorClient:
    """Protocol-like base for Cursor agent create / run / stream."""

    def create_agent(
        self, repo_url: str, prompt: str, env: dict | None = None
    ) -> str:
        return self.create_agent_with_run(repo_url, prompt, env)[0]

    def create_agent_with_run(
        self, repo_url: str, prompt: str, env: dict | None = None
    ) -> tuple[str, str | None]:
        raise NotImplementedError

    def create_run(self, agent_id: str, text: str) -> str:
        raise NotImplementedError

    def stream(self, agent_id: str, run_id: str) -> Iterator[str]:
        raise NotImplementedError


class HttpCursorClient(CursorClient):
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = API_BASE,
        sleep: Callable[[float], None] | None = None,
        busy_wait: float = 0.0,
        max_busy_retries: int = 5,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._sleep = sleep or (lambda _s: None)
        self._busy_wait = busy_wait
        self._max_busy_retries = max_busy_retries
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=self._base_url,
            timeout=httpx.Timeout(120.0, connect=30.0),
        )

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    def _auth(self) -> httpx.Auth | tuple[str, str]:
        return (self._api_key, "")

    def create_agent_with_run(
        self, repo_url: str, prompt: str, env: dict | None = None
    ) -> tuple[str, str | None]:
        body: dict[str, Any] = {
            "prompt": {"text": prompt},
            "repos": [{"url": repo_url}],
        }
        if env is not None:
            body["env"] = env
        response = self._client.post(
            "/v1/agents",
            json=body,
            headers=self._auth_headers(),
            auth=self._auth(),
        )
        response.raise_for_status()
        data = response.json()
        agent = data.get("agent") if isinstance(data.get("agent"), dict) else {}
        run = data.get("run") if isinstance(data.get("run"), dict) else {}
        agent_id = str(data.get("id") or data.get("agent_id") or agent.get("id"))
        run_id = run.get("id") or agent.get("latestRunId")
        return agent_id, str(run_id) if run_id else None

    def create_run(self, agent_id: str, text: str) -> str:
        last_error: Exception | None = None
        for attempt in range(self._max_busy_retries):
            response = self._client.post(
                f"/v1/agents/{agent_id}/runs",
                json={"prompt": {"text": text}},
                headers=self._auth_headers(),
                auth=self._auth(),
            )
            if response.status_code in (409, 429, 503):
                body_text = response.text.lower()
                retryable = (
                    response.status_code in (429, 503)
                    or "agent_busy" in body_text
                )
                if retryable:
                    last_error = httpx.HTTPStatusError(
                        f"cursor_retry_{response.status_code}",
                        request=response.request,
                        response=response,
                    )
                    if attempt + 1 < self._max_busy_retries:
                        wait = self._busy_wait or 2.0
                        if response.status_code == 429:
                            wait = max(wait, 5.0)
                        self._sleep(wait)
                        continue
                    raise last_error
            response.raise_for_status()
            data = response.json()
            run = data.get("run") if isinstance(data.get("run"), dict) else {}
            return str(data.get("id") or data.get("run_id") or run.get("id"))
        if last_error is not None:
            raise last_error
        raise RuntimeError("create_run failed without response")

    def stream(self, agent_id: str, run_id: str) -> Iterator[str]:
        with self._client.stream(
            "GET",
            f"/v1/agents/{agent_id}/runs/{run_id}/stream",
            headers=self._auth_headers(),
            auth=self._auth(),
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                yield line

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
