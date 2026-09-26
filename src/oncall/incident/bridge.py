"""Parse Cursor SSE and yield spoken chunks for the phone call."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator

STILL_WORKING = "Still working."

_PHASE_DONE = frozenset({"completed", "complete"})
_TOOL_STARTED = frozenset({"started", "running", "in_progress"})


def parse_sse(lines: Iterable[str]) -> Iterator[dict]:
    """Parse event/data pairs from SSE text lines. data is JSON."""
    event: str | None = None
    data_parts: list[str] = []

    def flush() -> dict | None:
        nonlocal event, data_parts
        if event is None or not data_parts:
            event = None
            data_parts = []
            return None
        raw = "\n".join(data_parts)
        parsed = json.loads(raw) if raw else {}
        item = {"event": event, "data": parsed}
        event = None
        data_parts = []
        return item

    for line in lines:
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        line = line.rstrip("\r\n")
        if line == "":
            item = flush()
            if item is not None:
                yield item
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event = line[6:].lstrip()
        elif line.startswith("data:"):
            data_parts.append(line[5:].lstrip())

    item = flush()
    if item is not None:
        yield item


class Bridge:
    def __init__(
        self,
        on_phase: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self._on_phase = on_phase

    def consume(self, lines: Iterable[str]) -> Iterator[str]:
        """Yield spoken chunks from an SSE line stream."""
        seen_call_ids: set[str] = set()

        for item in parse_sse(lines):
            event = item.get("event")
            data = item.get("data") or {}

            if event == "assistant":
                text = data.get("text")
                if text:
                    yield text
                continue

            if event == "thinking":
                continue

            if event == "tool_call":
                name = str(data.get("name") or "")
                status = str(data.get("status") or "").lower()
                args = data.get("args") or data.get("arguments") or {}
                if not isinstance(args, dict):
                    args = {}
                call_id = str(
                    data.get("callId")
                    or data.get("call_id")
                    or data.get("id")
                    or ""
                )

                if name == "phase" and status in _PHASE_DONE:
                    if self._on_phase is not None:
                        value = str(args.get("value") or "")
                        issue = str(args.get("issue") or "")
                        solution = str(args.get("solution") or "")
                        self._on_phase(value, issue, solution)
                    continue

                if name != "phase" and status in _TOOL_STARTED:
                    if call_id and call_id in seen_call_ids:
                        continue
                    if call_id:
                        seen_call_ids.add(call_id)
                    yield STILL_WORKING
                continue
