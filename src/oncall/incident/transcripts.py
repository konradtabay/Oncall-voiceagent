"""Fetch and format ElevenLabs conversation transcripts."""

from __future__ import annotations

import re
from typing import Any

import httpx

_CONV_ID = re.compile(r'conversation_id" value="(conv_[^"]+)"', re.I)


def conversation_id_from_twiml(twiml: str) -> str:
    match = _CONV_ID.search(twiml)
    return match.group(1) if match else ""


def fetch_conversation(api_key: str, conversation_id: str) -> dict[str, Any]:
    response = httpx.get(
        f"https://api.elevenlabs.io/v1/convai/conversations/{conversation_id}",
        headers={"xi-api-key": api_key},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def format_transcript_text(detail: dict[str, Any]) -> str:
    lines: list[str] = []
    for turn in detail.get("transcript") or []:
        role = turn.get("role", "?")
        msg = (turn.get("message") or "").strip()
        if msg:
            lines.append(f"[{role}] {msg}")
        for tc in turn.get("tool_calls") or []:
            name = tc.get("tool_name") or "tool"
            params = tc.get("params_as_json") or tc.get("parameters") or ""
            lines.append(f"[{role}] TOOL {name} {params}")
    return "\n".join(lines)
