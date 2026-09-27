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

from oncall.incident.voice import CLOSING_CTA, KEEP_UPDATED

VOICE_PROMPT = (
    "You are the on-call voice agent on a live incident call with the Maintainer. "
    "You are allowed and expected to run the approved fix for them. "
    "You do not SSH yourself; you start the fix by calling the phase tool with value "
    "execute, and the engineering backend runs the commands. "
    "Never say you cannot run commands, cannot access their systems, or are only an AI "
    "assistant who cannot help — that is wrong for this product. "
    "If they ask you to fix it, do it, run it, go ahead, or say yes, call phase execute "
    "immediately (once). "
    "Speak in plain language a fifteen-year-old follows. "
    "Keep answers concise but complete: two or three short sentences, about 40 to 55 "
    "words. Answer what they asked with enough context to be useful, not a lecture. "
    "No long lists or full pipeline tours unless they ask for an overview. "
    "Never say the word brief. "
    "System and business background: {{project}}. "
    "What broke on this incident (technical): {{brief}}. "
    "The one fix to run: {{fix}}. "
    "When they ask how something fits, use project and incident context in plain "
    "language — do not repeat the opening; give the main point plus one supporting detail. "
    f"After the proposed fix, end with: {CLOSING_CTA} "
    "If they say yes or agree to run it, call the phase tool once with value execute. "
    "Do not invent a second fix. "
    "Do not claim the process is back until the updates tool returns the fix sentence. "
    "When it does, speak that sentence out loud word for word and do not call updates again. "
    "Only call phase with value drop if they clearly want to end the call "
    "(hang up, goodbye, stop calling me, not interested in continuing). "
    "Never drop because they are annoyed, busy, or said they do not want to hear "
    "more explanation — use skip_turn or one short line, then wait. "
    "Do not drop for hold on, one sec, wait, I'll be back, or background noise. "
    "Do not repeat the full fix after the opening; if they already heard it, wait for yes or no. "
    "Never ask if they are still there, can hear you, or are on the line. "
    "Do not speak on a timer or just because it is quiet. "
    "Only speak when you have something important or relevant, or when answering them. "
    "If you have nothing important to add, call skip_turn and stay silent. "
    f"After phase execute, say exactly: {KEEP_UPDATED} "
    "Then call updates and wait in silence. "
    "When updates returns a sentence, speak that sentence out loud immediately. "
    "That is the fix result. Do not call skip_turn after it returns text. "
    "If updates says there is no update yet, call updates again and say nothing. "
    "Do not fill the silence. Do not say you are still working."
)

DEFAULT_OPENING = f"Hey. Something failed. The fix is Restart it. {CLOSING_CTA}"

FIRST_MESSAGE = "{{opening}}"

TURN_CONFIG = {
    "turn_timeout": 30,
    "turn_eagerness": "patient",
    "silence_end_call_timeout": -1,
    "soft_timeout_config": {
        "timeout_seconds": -1,
        "message": " ",
        "use_llm_generated_message": False,
    },
}

# Ambient typing under speech. The call stays on this agent while the fix runs.
BACKGROUND_SOUND = {
    "source_type": "preset",
    "source_id": "typing",
    "volume": 0.28,
    "crossfade_loop": True,
}

SKIP_TURN_TOOL = {
    "type": "system",
    "name": "skip_turn",
    "description": (
        "User is silent, thinking, or on hold, or you have nothing important "
        "to say. Stay silent until they speak. Do not pad with extra explanation."
    ),
    "params": {"system_tool_type": "skip_turn"},
}


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


def updates_tool(public_base: str) -> dict:
    return {
        "type": "webhook",
        "name": "updates",
        "description": (
            "Wait for the fix result after execute. "
            "When this returns a sentence, speak that sentence out loud word for word "
            "and do not call this tool again. If it says no update yet, call it again "
            "and stay silent."
        ),
        "response_timeout_secs": 60,
        "tool_call_sound_behavior": "auto",
        "api_schema": {
            "url": f"{public_base}/elevenlabs/updates",
            "method": "POST",
            "request_body_schema": {
                "type": "object",
                "properties": {
                    "incident_id": {
                        "type": "string",
                        "description": "Incident id. Always use {{incident_id}}.",
                    },
                },
                "required": [],
            },
        },
    }


def phase_tool(public_base: str) -> dict:
    return {
        "type": "webhook",
        "name": "phase",
        "description": (
            "Control the incident. Call execute when the Maintainer wants the fix run "
            "(yes, do it, fix it, go ahead, run it). That starts the real fix on the "
            "backend — you are authorized to call it."
        ),
        "response_timeout_secs": 45,
        "tool_call_sound": "typing",
        "tool_call_sound_behavior": "always",
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
                        "description": "Short issue in plain language.",
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
            "turn": TURN_CONFIG,
            "conversation": {
                "background_sound": BACKGROUND_SOUND,
            },
            "agent": {
                "first_message": FIRST_MESSAGE,
                "dynamic_variables": {
                    "dynamic_variable_placeholders": {
                        "incident_id": "unknown",
                        "brief": "Something failed.",
                        "fix": "Restart it.",
                        "project": "Sovereign Canadian AI training pipeline on-call.",
                        "opening": DEFAULT_OPENING,
                    }
                },
                "prompt": {
                    "prompt": VOICE_PROMPT,
                    "llm": "gemini-2.5-flash",
                    "temperature": 0.2,
                    "tools": [phase_tool(public), updates_tool(public)],
                    "built_in_tools": {"skip_turn": SKIP_TURN_TOOL},
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
    # Full agent patch often clears skip_turn; enable it explicitly.
    r2 = httpx.patch(
        f"https://api.elevenlabs.io/v1/convai/agents/{agent_id}",
        headers={"xi-api-key": key},
        json={
            "conversation_config": {
                "agent": {"prompt": {"built_in_tools": {"skip_turn": SKIP_TURN_TOOL}}},
            }
        },
        timeout=60,
    )
    if r2.status_code >= 400:
        print(r2.status_code, r2.text[:800], file=sys.stderr)
        return 1
    prompt = r.json()["conversation_config"]["agent"]["prompt"]
    print(prompt.get("llm"))
    print(f"{public}/elevenlabs/phase")
    return 0


if __name__ == "__main__":
    sys.exit(main())
