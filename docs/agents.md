# Coding agents

Two models, two jobs:

| Role | Who | Config |
| --- | --- | --- |
| **Voice** | Speaks on the phone | ElevenLabs agent (`oncall voice sync`) |
| **Implementer** | Diagnoses and applies the fix in `REPO_URL` | `AGENT=cursor` or `AGENT=webhook` |

This repo does not ship Anthropic, OpenAI, or Codex SDKs. The implementer is pluggable.

## Cursor

```env
AGENT=cursor
CURSOR_API_KEY=...
REPO_URL=https://github.com/your-org/your-service
```

Cursor picks the model. The repo must be linked to your Cursor account for private GitHub access.

## Webhook

Your service receives JSON:

```json
{
  "repo_url": "https://github.com/your-org/your-service",
  "instructions": "Diagnose or fix prompt text…",
  "verify_target": "https://your-service/health"
}
```

Respond with:

```json
{
  "text": "One sentence for the caller, or multi-line diagnosis text for the first call.",
  "ok": true
}
```

Set `ok` to `false` when the fix failed. `text` should still explain what happened.

After the maintainer says yes on the call, the same webhook receives fix instructions. Return **one short spoken sentence** when possible (the voice agent reads it aloud).

Fixes can take minutes. The ElevenLabs agent keeps calling `/elevenlabs/updates` until your process publishes the result.

## Example handler

[examples/agent_webhook.py](../examples/agent_webhook.py) runs `AGENT_COMMAND` with instructions on stdin:

```bash
export AGENT_COMMAND='claude -p'
python3 examples/agent_webhook.py
export AGENT_WEBHOOK_URL=http://127.0.0.1:9000/run
export AGENT=webhook
```

Use any command that prints agent output to stdout.
