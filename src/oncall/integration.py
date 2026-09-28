"""Quick-start and AI integration copy for humans and coding agents."""

from __future__ import annotations

import subprocess
from pathlib import Path

from oncall.config import Settings

_REPO_ROOT = Path(__file__).resolve().parents[2]


def git_remote_url() -> str:
    try:
        out = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""


def human_quickstart() -> str:
    return """On-call voice — quick start

1. Install
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e ".[dev]"
   cp .env.example .env

2. Fill .env (see .env.example groups: server, database, runtime, phone, voice, agent)

3. Expose the app (Twilio and ElevenLabs need HTTPS)
   oncall serve
   ngrok http 8000
   Set PUBLIC_BASE_URL in .env to the ngrok https URL

4. Sync the voice agent to your public URL
   oncall voice sync

5. Validate
   oncall check
   oncall check --live

6. Test an alert (uses Twilio + ElevenLabs credits)
   oncall integration snippet alert

Docs: docs/setup.md  |  Coding agents: docs/agents.md
For an AI assistant: run `oncall agent quickstart` and paste the output into the chat.
"""


def agent_quickstart_prompt(*, settings: Settings | None = None) -> str:
    origin = git_remote_url()
    repo_hint = (settings.repo_url if settings else "") or origin or "https://github.com/your-org/your-service"
    public = (settings.public_base_url if settings else "") or "https://YOUR_PUBLIC_HTTPS_URL"
    return f"""Integrate on-call voice for this project.

You are wiring the on-call-voice orchestrator (this repo) to the user's runtime and monitor.
Work in order. Do not skip validation steps.

## Goal

When their service fails a health check, POST /alerts opens an incident, diagnoses, calls the maintainer,
and runs an approved fix via AGENT=cursor or AGENT=webhook.

## Checklist

1. **Install** (in the oncall-voice repo root)
   - python3 -m venv .venv && source .venv/bin/activate
   - pip install -e ".[dev]"
   - cp .env.example .env if missing

2. **Runtime** — set in .env:
   - REPO_URL={repo_hint}
   - DATABASE_PATH=oncall.sqlite3 (or a persistent path on their server)
   - AGENT=cursor (CURSOR_API_KEY) or AGENT=webhook (AGENT_WEBHOOK_URL + examples/agent_webhook.py)

3. **Server**
   - PUBLIC_BASE_URL={public}  (must be https; not localhost)
   - Run: oncall serve (port 8000, single process)
   - Tunnel if local: ngrok http 8000, then update PUBLIC_BASE_URL

4. **Twilio** — TWILIO_* and MAINTAINER_NUMBER (E.164). Trial accounts: verify callee numbers in Twilio console.

5. **ElevenLabs** — ELEVENLABS_API_KEY; run `oncall voice sync` (creates agent id if empty).

6. **Secure alerts** — set ALERT_TOKEN; send Authorization: Bearer <token> on POST /alerts.

7. **Wire their monitor** — on failure, POST JSON to $PUBLIC_BASE_URL/alerts:
   ```json
   {{
     "summary": "short failure title",
     "logs": "recent log lines or error text",
     "verify_target": "https://their-service/health",
     "to_number": "+1..." 
   }}
   ```
   Omit to_number to use MAINTAINER_NUMBER from .env.

8. **Verify**
   - oncall check && oncall check --live
   - Use `oncall integration snippet alert` for a ready curl command after .env is filled.

9. **In the user's application repo** (REPO_URL, not necessarily this repo)
   - Add or document the health URL used as verify_target.
   - Optionally add a small script/cron that curls health and POSTs /alerts on failure (see docs/setup.md).

When finished, summarize what you set in .env (names only, never secret values) and how their monitor triggers /alerts.
"""


def alert_curl_snippet(settings: Settings) -> str:
    public = settings.public_base_url.rstrip("/")
    token = settings.alert_token
    number = settings.maintainer_number or "+1MAINTAINER"
    auth = ""
    if token:
        auth = f'  -H "Authorization: Bearer {token}" \\\n'
    return f"""# Test alert (spends Twilio + ElevenLabs). Load .env first or export vars.
curl -sS -X POST "{public}/alerts" \\
  -H 'Content-Type: application/json' \\
{auth}  -d '{{"summary":"Worker down","logs":"exit 1","verify_target":"https://example.com/health","to_number":"{number}"}}'
"""


def health_monitor_snippet(settings: Settings) -> str:
    public = settings.public_base_url.rstrip("/")
    token = settings.alert_token
    health = "https://your-service/health"
    auth_header = ""
    if token:
        auth_header = f'  -H "Authorization: Bearer {token}" \\\n'
    return f"""# Example cron-friendly monitor (adjust HEALTH_URL and paths)
HEALTH_URL="{health}"
PUBLIC_BASE_URL="{public}"
if ! curl -sf "$HEALTH_URL"; then
  curl -sS -X POST "$PUBLIC_BASE_URL/alerts" \\
    -H 'Content-Type: application/json' \\
{auth_header}    -d '{{"summary":"health check failed","logs":"curl exit non-zero","verify_target":"'"$HEALTH_URL"'"}}'
fi
"""
