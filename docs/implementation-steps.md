# Implementation steps

This file is the map for **building, running, and extending** the on-call voice orchestrator. Product behavior stays in [DESIGN.md](../DESIGN.md). Frozen cross-component messages stay in [src/oncall/seam.py](../src/oncall/seam.py). Per-track agent instructions stay in [docs/components/](components/).

If this map and a component brief disagree about that component, the component brief wins. If two briefs disagree about a handoff, [components/00-seam.md](components/00-seam.md) wins.

## Build status (this repo)

All five tracks below are **implemented** under `src/oncall/` and covered by `tests/`. You do not need to re-implement them to run the service. Use the component briefs only when **changing** a track or onboarding a parallel coding agent.

| Track | Code | Tests |
| --- | --- | --- |
| Seam | [src/oncall/seam.py](../src/oncall/seam.py) | `tests/test_seam.py` |
| Telephony | [src/oncall/telephony/](../src/oncall/telephony/) | `tests/test_telephony.py` |
| Incident state | [src/oncall/incident/models.py](../src/oncall/incident/models.py), `store.py`, `machine.py`, `receipts.py` | `tests/test_state_machine.py` |
| Agent bridge | `cursor_client.py`, `bridge.py`, `prompts.py`, `guard.py` | `tests/test_bridge.py`, `tests/test_agent_contract.py` |
| Wiring | [src/oncall/app.py](../src/oncall/app.py), [config.py](../src/oncall/config.py), [incident/service.py](../src/oncall/incident/service.py) | `tests/test_wiring.py` |

**Runtime entry point:** `build_default_app()` in [src/oncall/app.py](../src/oncall/app.py) — loads `.env`, wires Twilio + ElevenLabs + Cursor + SQLite, mounts Twilio routes.

**Where talk happens:** ElevenLabs built-in model on the call. After ngrok or the prompt changes, run `python scripts/sync_elevenlabs_llm_url.py`. That sets the agent LLM and a `phase` webhook at `{PUBLIC_BASE_URL}/elevenlabs/phase`.

**Where Cursor attaches:** one cloud agent per incident at diagnose time (`CURSOR_API_KEY`, `CURSOR_REPO_URL`). A follow-up run starts only after the Maintainer confirms the fix (second `phase` `execute`) or when verify/fail needs the coding agent.

---

## Local build (first time)

From the repo root:

```bash
cd /path/to/Oncall-voiceagent
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Copy secrets from the template (never commit `.env`):

```bash
cp .env.example .env
# edit .env — see "Environment" below
```

Run the full test suite (no network, no API keys):

```bash
python -m pytest -q
```

---

## Environment

| Variable | Required | Purpose |
| --- | --- | --- |
| `TWILIO_ACCOUNT_SID` | yes | Twilio REST + webhook signature |
| `TWILIO_AUTH_TOKEN` | yes | Twilio REST + webhook signature |
| `TWILIO_FROM_NUMBER` | yes | E.164 outbound call + SMS from |
| `TWILIO_MACHINE_DETECTION` | no | Set `Enable` for AMD on **this app’s** outbound `calls.create` only; leave unset to disable |
| `MAINTAINER_NUMBER` | yes | Who to call/text (also pass as `to_number` on `/alerts` if you prefer) |
| `PUBLIC_BASE_URL` | yes | HTTPS base Twilio and ElevenLabs reach (e.g. ngrok) |
| `ELEVENLABS_API_KEY` | yes | `register-call` and agent API |
| `ELEVENLABS_AGENT_ID` | yes | Eleven Agents agent id (`agent_…`), **not** a voice id |
| `CURSOR_API_KEY` | yes | Cloud Agents API |
| `CURSOR_REPO_URL` | yes | Repo the cloud agent may change when fixing |
| `ELEVENLABS_VOICE_ID` | no | Only for API-created agents; telephony uses `ELEVENLABS_AGENT_ID` |
| `DATABASE_PATH` | no | Default `oncall.sqlite3` |

**ElevenLabs API key (dashboard):** **ElevenAgents → Write** (required for `register-call`). **Voices → Read** optional. Do not put real secrets in `.env.example`.

**ElevenLabs agent (not the same as API key):**

- Create in **Eleven Agents** UI, or `POST /v1/convai/agents/create` with `llm: custom-llm` and URL `{PUBLIC_BASE_URL}/v1/chat/completions`.
- Put the returned **`agent_id`** in `ELEVENLABS_AGENT_ID`.
- Backup/cascade LLM off. System prompt empty or minimal.

**Twilio (optional console):** Inbound SMS webhook → `{PUBLIC_BASE_URL}/twilio/sms` (POST). Outbound voice uses URLs set on `calls.create` by the app.

---

## Run (live stack)

**Terminal 1 — tunnel**

```bash
ngrok http 8000
# or, on a paid ngrok plan: ngrok http 8000 --domain=your-subdomain.ngrok-free.app
```

`PUBLIC_BASE_URL` must match the tunnel’s HTTPS URL (copy from the ngrok console). After it changes, sync ElevenLabs (dashboard or script):

```bash
python scripts/sync_elevenlabs_llm_url.py
```

If the agent still points at an old ngrok host, calls connect but stay **silent** then drop.

**Terminal 2 — API**

```bash
source .venv/bin/activate
uvicorn oncall.app:build_default_app --factory --host 0.0.0.0 --port 8000 --reload
```

**Sanity check**

```bash
curl -sS -o /dev/null -w "%{http_code}\n" "$PUBLIC_BASE_URL/docs"
```

Expect `200`.

**Fire an incident** (uses `MAINTAINER_NUMBER` from the shell if exported, or substitute `to_number`):

```bash
set -a && source .env && set +a
curl -sS -X POST "$PUBLIC_BASE_URL/alerts" \
  -H "Content-Type: application/json" \
  -d "{\"summary\":\"Worker down\",\"logs\":\"exit 1\",\"verify_target\":\"https://example/health\",\"to_number\":\"$MAINTAINER_NUMBER\"}"
```

Expect JSON with `incident_id` and `state` moving to `ringing` after Cursor diagnose. Your phone should ring.

**Manual staging health fixture** (optional local verify target): [fixtures/staging/README.md](../fixtures/staging/README.md).

---

## HTTP surface

| Method | Path | Who calls it |
| --- | --- | --- |
| POST | `/alerts` | Your monitor / you — opens or queues an Incident |
| POST | `/twilio/voice` | Twilio — human → ElevenLabs TwiML; miss → hangup |
| POST | `/twilio/status` | Twilio — miss reasons |
| POST | `/twilio/sms` | Twilio — inbound SMS |
| POST | `/v1/chat/completions` | ElevenLabs Custom LLM — speech turns |

---

## How to dispatch a coding agent (change one track)

Give the agent only:

1. This file (for context).
2. Their one brief under `docs/components/`.
3. [src/oncall/seam.py](../src/oncall/seam.py) when the brief says so.

Do not paste other components’ source. Run **their** tests until the brief’s “Done when” passes; wiring owner runs `python -m pytest -q` last.

| Agent | Brief | Owns |
| --- | --- | --- |
| Seam | [00-seam.md](components/00-seam.md) | `seam.py`, `test_seam.py` |
| Telephony | [01-telephony.md](components/01-telephony.md) | `telephony/`, `test_telephony.py` |
| Incident state | [02-incident-state.md](components/02-incident-state.md) | `machine.py`, `store.py`, …, `test_state_machine.py` |
| Agent bridge | [03-agent-bridge.md](components/03-agent-bridge.md) | `bridge.py`, `cursor_client.py`, … |
| Wiring | [04-wiring.md](components/04-wiring.md) | `app.py`, `service.py`, `test_wiring.py` |

Order for **new** work: seam → (telephony ∥ state ∥ bridge) → wiring.

---

## Decisions every agent inherits

- Twilio places the call and sends SMS. ElevenLabs does not dial. ElevenLabs is the custom LLM target at `POST /v1/chat/completions`. Backup LLM off.
- One Cursor cloud agent per Incident, created before the phone rings. Opening run: Brief + one Fix, no server change. Later turns: follow-up runs. `409 agent_busy` waits.
- Spoken audio = assistant SSE text. `thinking` and tools are not spoken. First assistant delta streams immediately. Non-`phase` tool start → speak `Still working.` once.
- Control = `phase` tool: `talking`, `execute`, `verified`, `failed`, `drop`. Bare “yes” is not Execute.
- Orchestrator never SSHes; deploy-like tools are gated by [guard.py](../src/oncall/incident/guard.py) until a Fix has started.
- One active Incident; queued alerts wait. Start Receipt does not close the Incident or open a Text Session.
- Inbound voice callback after Miss is rejected. Miss → Text Session only.

---

## Handoff picture

```text
Alert HTTP
  -> Wiring.open_alert
    -> Incident state.open_or_queue
    -> Agent bridge.create_agent / create_run / stream
    -> Incident state.ready_to_dial
      -> Dial
        -> Telephony.dial
          -> Twilio

Twilio voice webhook
  -> Telephony
    -> Answered | Missed
      -> Wiring.handle_event
        -> Incident state.on_answered | on_missed
          -> Hangup, SmsOut
            -> Telephony.hangup / sms_out

ElevenLabs POST /v1/chat/completions
  -> Wiring.completion
    -> Agent bridge.stream + Bridge.consume
      -> spoken chunks back to ElevenLabs
      -> phase callback
        -> Incident state.on_phase
          -> SmsOut, Hangup
            -> Telephony

Twilio inbound SMS
  -> Telephony
    -> SmsIn
      -> Wiring.handle_event
        -> Incident state.on_sms
          -> "turn" or "follow_up"
            -> Agent bridge run
              -> SmsOut
                -> Telephony.sms_out
```

Wiring is the only component that calls the other three. Telephony does not import incident. Incident state does not import telephony, Cursor, or the bridge. The bridge does not import the state machine.

---

## Validation checklist

**CI (offline)**

```bash
python -m pytest -q
```

**Vendor APIs (with `.env` loaded)**

```bash
python scripts/smoke_vendors.py
```

Expect Twilio, Cursor, ElevenLabs agent, and `register-call` → `200`. `app_docs` → `200` only while **both** uvicorn and your tunnel run and `PUBLIC_BASE_URL` matches the tunnel.

Manual equivalents:

- Twilio: `GET /2010-04-01/Accounts/{SID}.json` → 200
- Cursor: `GET /v1/me` → 200
- ElevenLabs: `GET /v1/convai/agents/{ELEVENLABS_AGENT_ID}` → 200
- ElevenLabs: `POST /v1/convai/twilio/register-call` → 200
- App: `{PUBLIC_BASE_URL}/docs` → 200 while uvicorn + ngrok run

**Live call** (human): answer → hear Brief/Fix → Execute → stay on line through Verify → closing SMS. See [fixtures/staging/README.md](../fixtures/staging/README.md).

---

## Related docs

- [DESIGN.md](../DESIGN.md) — product loop
- [CONTEXT.md](../CONTEXT.md) — glossary
- [docs/adr/0001-twilio-carries-the-call-cursor-speaks.md](adr/0001-twilio-carries-the-call-cursor-speaks.md) — vendor split
- [.env.example](../.env.example) — env template (no secrets)
