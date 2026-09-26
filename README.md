# On-call voice orchestrator

When a watched process fails, the Maintainer gets a **Twilio** call. **ElevenLabs** handles voice; a **Cursor cloud agent** diagnoses, speaks on the line, and can fix the repo you point at.

**Build and run:** [docs/implementation-steps.md](docs/implementation-steps.md) (source of truth for setup, env, HTTP surface, and parallel agent tracks).

**Product behavior:** [DESIGN.md](DESIGN.md) · **Glossary:** [CONTEXT.md](CONTEXT.md) · **Vendor split:** [docs/adr/0001-twilio-carries-the-call-cursor-speaks.md](docs/adr/0001-twilio-carries-the-call-cursor-speaks.md)

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill secrets
python -m pytest -q
uvicorn oncall.app:build_default_app --factory --host 0.0.0.0 --port 8000
```

Point `PUBLIC_BASE_URL` at your HTTPS tunnel (e.g. ngrok). ElevenLabs agent **Custom LLM** → `{PUBLIC_BASE_URL}/v1/chat/completions`.

## Parallel coding agents

Each track has a brief under [docs/components/](docs/components/). Dispatch one agent per brief; wiring runs full `pytest` last. See the table in [implementation-steps.md](docs/implementation-steps.md#how-to-dispatch-a-coding-agent-change-one-track).
