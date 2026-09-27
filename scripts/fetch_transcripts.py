#!/usr/bin/env python3
"""Print recent ElevenLabs call transcripts for the on-call agent (.env)."""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> int:
    _load_dotenv()
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    agent_id = os.environ.get("ELEVENLABS_AGENT_ID", "")
    if not key or not agent_id:
        print("Need ELEVENLABS_API_KEY and ELEVENLABS_AGENT_ID", file=sys.stderr)
        return 1
    limit = int(os.environ.get("TRANSCRIPT_LIMIT", "5"))
    headers = {"xi-api-key": key}
    listed = httpx.get(
        "https://api.elevenlabs.io/v1/convai/conversations",
        headers=headers,
        params={
            "agent_id": agent_id,
            "page_size": min(limit, 30),
            "summary_mode": "include",
        },
        timeout=30,
    )
    listed.raise_for_status()
    for row in listed.json().get("conversations", [])[:limit]:
        cid = row["conversation_id"]
        started = datetime.fromtimestamp(
            row.get("start_time_unix_secs", 0), tz=UTC
        ).strftime("%Y-%m-%d %H:%M UTC")
        print(f"\n{'=' * 72}")
        print(
            f"{cid}  {started}  {row.get('call_duration_secs', 0)}s  "
            f"{row.get('status')}  success={row.get('call_successful')}"
        )
        if row.get("transcript_summary"):
            print(f"Summary: {row['transcript_summary']}\n")
        detail = httpx.get(
            f"https://api.elevenlabs.io/v1/convai/conversations/{cid}",
            headers=headers,
            timeout=30,
        )
        if detail.status_code >= 400:
            print(f"(detail {detail.status_code})")
            continue
        for turn in detail.json().get("transcript", []):
            role = turn.get("role", "?")
            msg = (turn.get("message") or "").strip()
            if msg:
                print(f"[{role}] {msg}")
            for tc in turn.get("tool_calls") or []:
                name = tc.get("tool_name") or tc.get("type") or "tool"
                print(f"[{role}] TOOL {name} {tc.get('params_as_json') or ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
