#!/usr/bin/env python3
"""Vendor API checks from docs/implementation-steps.md (prints status codes only)."""

from __future__ import annotations

import json
import os
import sys
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
    results: dict[str, int | str] = {}
    sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    if sid and token:
        r = httpx.get(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}.json",
            auth=(sid, token),
            timeout=30,
        )
        results["twilio"] = r.status_code
    else:
        results["twilio"] = "skip"

    key = os.environ.get("CURSOR_API_KEY", "")
    if key:
        r = httpx.get(
            "https://api.cursor.com/v1/me",
            headers={"Authorization": f"Bearer {key}"},
            timeout=30,
        )
        results["cursor"] = r.status_code
    else:
        results["cursor"] = "skip"

    el_key = os.environ.get("ELEVENLABS_API_KEY", "")
    agent_id = os.environ.get("ELEVENLABS_AGENT_ID", "")
    if el_key and agent_id:
        r = httpx.get(
            f"https://api.elevenlabs.io/v1/convai/agents/{agent_id}",
            headers={"xi-api-key": el_key},
            timeout=30,
        )
        results["elevenlabs_agent"] = r.status_code
        r2 = httpx.post(
            "https://api.elevenlabs.io/v1/convai/twilio/register-call",
            headers={"xi-api-key": el_key},
            json={
                "agent_id": agent_id,
                "from_number": "+10000000000",
                "to_number": "+10000000001",
            },
            timeout=30,
        )
        results["elevenlabs_register"] = r2.status_code
    else:
        results["elevenlabs_agent"] = "skip"
        results["elevenlabs_register"] = "skip"

    pub = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    if pub:
        try:
            r = httpx.get(f"{pub}/docs", timeout=15, follow_redirects=True)
            results["app_docs"] = r.status_code
        except httpx.HTTPError as exc:
            results["app_docs"] = f"error:{type(exc).__name__}"
    else:
        results["app_docs"] = "skip"

    print(json.dumps(results, indent=2))
    vendor_keys = ("twilio", "cursor", "elevenlabs_agent", "elevenlabs_register")
    vendor_codes = [
        results[k] for k in vendor_keys if isinstance(results.get(k), int)
    ]
    if not vendor_codes or not all(c == 200 for c in vendor_codes):
        return 1
    app = results.get("app_docs")
    if isinstance(app, int) and app != 200:
        print(
            "app_docs not 200: run uvicorn and an HTTPS tunnel; "
            "set PUBLIC_BASE_URL to the tunnel URL (free ngrok cannot use a reserved subdomain).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
