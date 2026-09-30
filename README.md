# On-call

Voice agent that calls you the moment a training run dies. You talk to it, and it deploys the fix over the phone, from wherever you are.

https://github.com/user-attachments/assets/cf582145-422d-4d0f-b7ee-9e362e37147e

[Full video](https://drive.google.com/drive/home)

## What it does

An alert opens one incident. It carries the logs and enough context to name the failure and one fix. The call does not start until that is ready, so the first thing they hear is the problem and the fix, in plain language.

When they tell it to run the fix, a text goes out, the coding agent applies the fix against your repo, and the voice agent speaks the result on the call.

## Quick start

Install, then let a coding agent do the wiring:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
oncall agent quickstart
```

Paste the output into Cursor, Claude Code, or Codex. It walks through `.env`, tunnel, voice sync, and hooking your monitor to `/alerts`. See [AGENTS.md](AGENTS.md) and [docs/agent-quickstart.md](docs/agent-quickstart.md).

After `.env` is ready:

```bash
oncall integration snippet alert    # test POST /alerts
oncall integration snippet monitor  # cron-style health hook
```

### Manual setup

```bash
oncall quickstart    # human checklist in the terminal
oncall check
oncall voice sync    # after PUBLIC_BASE_URL is https
oncall serve
```

Full walkthrough: [docs/setup.md](docs/setup.md). Coding agent backends: [docs/agents.md](docs/agents.md).

## Where companies use it

- A worker dies overnight. One call: what broke, one fix, yes, then health is back on the line.
- A webhook or queue consumer stalls. Same loop with your monitor posting to `/alerts`.
- A small team with one on-call number. One open incident; the next alert waits in queue.

## Connect

| Piece | Env |
| --- | --- |
| Server (HTTPS) | `PUBLIC_BASE_URL` |
| Database | `DATABASE_PATH` (SQLite file) |
| Runtime | `REPO_URL` + per-alert `verify_target` |
| Phone | Twilio vars + `MAINTAINER_NUMBER` |
| Voice | `ELEVENLABS_*` — run `oncall voice sync` after URL changes |
| Coding agent | `AGENT=cursor` or `AGENT=webhook` |
