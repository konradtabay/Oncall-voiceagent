"""Sync ElevenLabs agent tools and prompt to PUBLIC_BASE_URL."""

from __future__ import annotations

import os
import sys
from typing import Any

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


def updates_tool(public_base: str) -> dict[str, Any]:
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


def phase_tool(public_base: str) -> dict[str, Any]:
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


def _agent_payload(public: str) -> dict[str, Any]:
    return {
        "conversation_config": {
            "turn": TURN_CONFIG,
            "conversation": {"background_sound": BACKGROUND_SOUND},
            "agent": {
                "first_message": FIRST_MESSAGE,
                "dynamic_variables": {
                    "dynamic_variable_placeholders": {
                        "incident_id": "unknown",
                        "brief": "Something failed.",
                        "fix": "Restart it.",
                        "project": "Your service and on-call context.",
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
            },
        }
    }


def sync_agent(
    *,
    api_key: str,
    agent_id: str,
    public_base_url: str,
    create_if_missing: bool = True,
) -> tuple[str, str]:
    """Patch agent tools. Create agent when id is empty and create_if_missing."""
    public = public_base_url.strip().rstrip("/")
    if not api_key or not public:
        raise ValueError("ELEVENLABS_API_KEY and PUBLIC_BASE_URL are required")
    headers = {"xi-api-key": api_key}
    with httpx.Client(timeout=60.0) as client:
        if not agent_id.strip() and create_if_missing:
            r = client.post(
                "https://api.elevenlabs.io/v1/convai/agents/create",
                headers=headers,
                json={"name": "oncall-voice", **_agent_payload(public)},
            )
            r.raise_for_status()
            agent_id = str(r.json().get("agent_id") or r.json().get("id") or "")
            if not agent_id:
                raise RuntimeError("ElevenLabs create did not return agent_id")
            print(f"Created agent. Set ELEVENLABS_AGENT_ID={agent_id}", file=sys.stderr)
        elif not agent_id.strip():
            raise ValueError("ELEVENLABS_AGENT_ID is empty")
        else:
            r = client.patch(
                f"https://api.elevenlabs.io/v1/convai/agents/{agent_id}",
                headers=headers,
                json=_agent_payload(public),
            )
            if r.status_code >= 400:
                raise RuntimeError(f"{r.status_code} {r.text[:800]}")
            r2 = client.patch(
                f"https://api.elevenlabs.io/v1/convai/agents/{agent_id}",
                headers=headers,
                json={
                    "conversation_config": {
                        "agent": {
                            "prompt": {"built_in_tools": {"skip_turn": SKIP_TURN_TOOL}}
                        },
                    }
                },
            )
            if r2.status_code >= 400:
                raise RuntimeError(f"{r2.status_code} {r2.text[:800]}")
            llm = r.json()["conversation_config"]["agent"]["prompt"].get("llm", "")
            print(llm)
    return agent_id, f"{public}/elevenlabs/phase"
