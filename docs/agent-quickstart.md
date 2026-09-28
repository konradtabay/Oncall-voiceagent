# Agent quick start

For **Cursor, Claude Code, Codex**, or any coding agent integrating on-call voice for a user.

## One command

From the oncall-voice repo (with venv active):

```bash
oncall agent quickstart
```

Paste the printed block into the agent chat. It is a ordered checklist: `.env`, tunnel, voice sync, monitor → `/alerts`.

Human-oriented steps: `oncall quickstart`.

## What the agent should produce

1. A filled `.env` (from `.env.example`) — report **variable names only**, never secrets.
2. `REPO_URL` pointing at the **service repo** the fix agent may change.
3. A **verify_target** URL the agent can hit after a fix (public HTTPS, not localhost).
4. A **monitor hook**: cron, CI, or app code that POSTs to `/alerts` on failure.
5. Confirmation that `oncall check` passes (and `oncall check --live` when the tunnel is up).

## Alert contract

`POST {PUBLIC_BASE_URL}/alerts`

| Field | Required | Purpose |
| --- | --- | --- |
| `summary` | yes | Short title for the call |
| `logs` | yes | Context for diagnosis |
| `verify_target` | yes | Health URL after the fix |
| `to_number` | no | E.164; defaults to `MAINTAINER_NUMBER` |
| `incident_id` | no | Idempotency while incident open |

Optional header: `Authorization: Bearer $ALERT_TOKEN`

## Snippets for the agent to run

```bash
oncall integration snippet alert    # curl test after .env is ready
oncall integration snippet monitor  # bash health loop template
```

## Coding agent backend

- **Cursor**: `AGENT=cursor`, `CURSOR_API_KEY`, GitHub repo linked in Cursor.
- **Anything else**: `AGENT=webhook`, run [examples/agent_webhook.py](../examples/agent_webhook.py), set `AGENT_WEBHOOK_URL`.

Voice on the phone is **ElevenLabs** (`oncall voice sync`). That is separate from the coding agent.

See also [agents.md](agents.md) and [setup.md](setup.md).
