#!/usr/bin/env python3
"""Point the ElevenLabs agent at a built-in conversation model and the phase webhook.

ElevenLabs speaks on the call. Cursor runs only when this app's /elevenlabs/phase
tool is called with a confirmed execute (or verified / failed / drop).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

VOICE_PROMPT = (
    "You are on a phone call with the Maintainer. "
    "Speak in plain language a fifteen-year-old follows. "
    "The brief is: {{brief}}. "
    "The one fix is: {{fix}}. "
    "Ask if they want anything else changed before you run the fix. "
    "When they agree to run it, call the phase tool with value execute. "
    "If they then say there is nothing else, call phase with value execute again. "
    "Do not invent a second fix. "
    "Do not claim the process is back until the phase tool tells you it succeeded. "
    "If they want to stop, call phase with value drop."
)

FIRST_MESSAGE = (
    "{{brief}} The fix is {{fix}}. Anything else before I run the fix?"
)


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


def phase_tool(public_base: str) -> dict:
    return {
        "type": "webhook",
        "name": "phase",
        "description": (
            "Tell the on-call system the conversation phase. "
            "execute the first time arms the fix. "
            "execute again after they say nothing else starts the engineering agent."
        ),
        "response_timeout_secs": 20,
        "api_schema": {
            "url": f"{public_base}/elevenlabs/phase",
            "method": "POST",
            "request_body_schema": {
                "type": "object",
                "properties": {
                    "incident_id": {
                        "type": "string",
                        "description": "Incident id. Always use {{incident_id}}.",
                    },
                    "value": {
                        "type": "string",
                        "description": "talking, execute, verified, failed, or drop",
                        "enum": ["talking", "execute", "verified", "failed", "drop"],
                    },
                    "issue": {
                        "type": "string",
                        "description": "Short issue, usually the brief.",
                    },
                    "solution": {
                        "type": "string",
                        "description": "Short fix.",
                    },
                },
                "required": ["value"],
            },
        },
    }


def main() -> int:
    _load_dotenv()
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    agent_id = os.environ.get("ELEVENLABS_AGENT_ID", "")
    public = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not key or not agent_id or not public:
        print("Need ELEVENLABS_API_KEY, ELEVENLABS_AGENT_ID, PUBLIC_BASE_URL", file=sys.stderr)
        return 1
    payload = {
        "conversation_config": {
            "agent": {
                "first_message": FIRST_MESSAGE,
                "dynamic_variables": {
                    "dynamic_variable_placeholders": {
                        "incident_id": "unknown",
                        "brief": "Something failed.",
                        "fix": "Restart it.",
                    }
                },
                "prompt": {
                    "prompt": VOICE_PROMPT,
                    "llm": "gemini-2.5-flash",
                    "temperature": 0.2,
                    "tools": [phase_tool(public)],
                    "custom_llm": None,
                },
            }
        }
    }
    r = httpx.patch(
        f"https://api.elevenlabs.io/v1/convai/agents/{agent_id}",
        headers={"xi-api-key": key},
        json=payload,
        timeout=60,
    )
    if r.status_code >= 400:
        print(r.status_code, r.text[:800], file=sys.stderr)
        return 1
    prompt = r.json()["conversation_config"]["agent"]["prompt"]
    print(prompt.get("llm"))
    print(f"{public}/elevenlabs/phase")
    return 0


if __name__ == "__main__":
    sys.exit(main())
