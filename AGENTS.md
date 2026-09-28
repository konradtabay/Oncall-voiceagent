# AI agent instructions

This repo is the **on-call voice orchestrator**. When the user asks to integrate, set up, or connect on-call voice:

1. Run **`oncall agent quickstart`** and follow the printed checklist end to end.
2. Read **[docs/agent-quickstart.md](docs/agent-quickstart.md)** for the `/alerts` contract and snippets.
3. Use **`oncall check`** after editing `.env`; use **`oncall check --live`** once `PUBLIC_BASE_URL` is reachable.

## Do not

- Commit `.env` or paste secrets into chat.
- Point `verify_target` at localhost if `AGENT=cursor` or a cloud webhook runs the fix.
- Skip **`oncall voice sync`** after changing `PUBLIC_BASE_URL`.

## Key files

| File | Role |
| --- | --- |
| `.env.example` | All configuration groups |
| `src/oncall/app.py` | `/alerts`, Twilio, ElevenLabs routes |
| `docs/setup.md` | Full human setup |
| `docs/agents.md` | Webhook JSON for coding agents |
| `examples/agent_webhook.py` | Minimal `AGENT=webhook` server |

## CLI

```bash
oncall quickstart              # human steps
oncall agent quickstart        # paste into AI chat
oncall integration snippet alert
oncall integration snippet monitor
oncall check [--live]
oncall serve
oncall voice sync
```
