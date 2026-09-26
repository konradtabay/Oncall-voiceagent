# Agent brief: Wiring

You connect the other three components. You do not reimplement their rules. If a phase rule, a Twilio status, or an SSE event is wrong, that bug belongs to the component that owns it.

Start only after the seam, telephony, incident state, and agent bridge briefs are done.

## Read

- [docs/implementation-steps.md](../implementation-steps.md)
- [docs/components/00-seam.md](00-seam.md)
- [docs/components/01-telephony.md](01-telephony.md) public API only
- [docs/components/02-incident-state.md](02-incident-state.md) public API only
- [docs/components/03-agent-bridge.md](03-agent-bridge.md) public API only
- This file

## Edit only

- `src/oncall/config.py`
- `src/oncall/app.py`
- `src/oncall/incident/service.py`
- `tests/test_wiring.py`

You may add a store lookup only if incident state already exported it. `latest_for_number` is part of that brief. Do not change phase rules, TwiML, or SSE parsing.

## Handoffs

### You receive

| Input | From | You call |
| --- | --- | --- |
| `POST /alerts` JSON `summary`, `logs`, `verify_target`, `to_number`, optional `incident_id` | Outside alert | `IncidentService.open_alert` |
| `Answered` | Telephony `on_event` | `machine.on_answered` |
| `Missed` | Telephony `on_event` | `machine.on_missed`, then perform the commands |
| `SmsIn` | Telephony `on_event` | `machine.on_sms` |
| `POST /v1/chat/completions` body `messages` | ElevenLabs | `IncidentService.completion` |
| Spoken chunks | `Bridge.consume` | OpenAI SSE response |
| Phase callback | You pass it into `Bridge` | `guard.on_phase`, then `machine.on_phase`, then perform the commands |
| Commands | Incident state | `telephony.dial`, `telephony.hangup`, or `telephony.sms_out` |

### You send

| Output | To | When |
| --- | --- | --- |
| `Dial` | `telephony.dial` | Diagnose run finished and `ready_to_dial` returned it |
| `Hangup` | `telephony.hangup` | A command from `on_missed`, `verified`, or `drop` |
| `SmsOut` | `telephony.sms_out` | Start Receipt, closing Receipt, Text Session open, Text Session turn, Follow-up answer |
| `{"incident_id", "state"}` | `POST /alerts` | After `open_alert`. Queued alerts return state `queued` and do not dial. |
| OpenAI chat-completion SSE | ElevenLabs | Each spoken chunk as `choices[0].delta.content`, then `data: [DONE]` |
| Create-agent and create-run | `CursorClient` | One agent per Incident, before dial. Diagnose text includes the summary, logs, verify target, and `DIAGNOSE_INSTRUCTION`, and asks for a final line starting `Fix: `. |

`on_event` returns `None`. Do not also return a TwiML message body for the same reply you sent with `sms_out`.

## Service behavior

```text
class IncidentService:
    __init__(store, machine, cursor, telephony, *, repo_url)
    open_alert(...) -> Incident
    handle_event(Answered | Missed | SmsIn) -> None
    completion(messages) -> Iterator[str]
```

`open_alert`: build an `Incident` and call `open_or_queue`. If it was saved as `diagnosing`, create the Cursor agent with `AGENT_PROMPT` plus `DIAGNOSE_INSTRUCTION`, store `agent_id`, run the diagnose text through the bridge, split the spoken text on `Fix:`, then `ready_to_dial` and perform `Dial`. If it was not saved, it is queued: set the returned state's label to `queued` and do not dial.

`handle_event(Answered)` calls `on_answered` and performs no commands.

`handle_event(Missed)` performs whatever `on_missed` returns.

`handle_event(SmsIn)` finds the Incident with `latest_for_number(from_number)`, else `active()`. `on_sms` returns `turn` or `follow_up`.

- `turn` and the run is free: run that body and `sms_out` the spoken text with kind `text_turn`.
- `follow_up` and the run is free: pop the queued turn, run it, `sms_out` with kind `follow_up`.
- Run already locked: leave the text on the turn queue. Drain it when the current run finishes.

`completion`: the active Incident only. The first request for that Incident yields `"{brief} The fix is {fix}"` before any new run, so the opening line does not wait. A later user message is one follow-up run. If the run lock is held, enqueue the text and yield `Still working.`

One run at a time. `set_run_lock(True)` before `create_run`, `False` in a `finally`, then drain one queued turn.

Phase callback order: `DeployGuard.on_phase`, then `machine.on_phase`, then perform commands. On `verified` or `drop`, call `promote_queue`. If it returns an Incident, diagnose and dial that one.

Diagnosis split: strip `Still working.` Join on the first `Fix:`. The left side is the Brief. The right side is the Fix. If there is no `Fix:`, both are the cleaned text.

SSE bytes:

```text
data: {"choices":[{"index":0,"delta":{"content":"<chunk>"}}]}

data: [DONE]
```

## App

```text
create_app(service=None) -> FastAPI
  includes the telephony router
  binds service.telephony when service is passed
  POST /alerts
  POST /v1/chat/completions  -> StreamingResponse media_type text/event-stream

build_default_app()
  Settings.from_env()
  Store, Machine, HttpCursorClient, TwilioRestAdapter, ElevenLabsRegisterAdapter
  Telephony on_event points at the service
  voice URL {PUBLIC_BASE_URL}/twilio/voice
  status URL {PUBLIC_BASE_URL}/twilio/status
```

`Settings.from_env` reads `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `ELEVENLABS_API_KEY`, `ELEVENLABS_AGENT_ID`, `CURSOR_API_KEY`, `CURSOR_REPO_URL`, `PUBLIC_BASE_URL`, `DATABASE_PATH`, `MAINTAINER_NUMBER`. Missing values are empty strings. Defaults: public base `http://127.0.0.1:8000`, database `oncall.sqlite3`.

## Tests

`tests/test_wiring.py` uses a temp database, a scripted `CursorClient`, and fake Twilio and ElevenLabs ports. No network.

Scripted diagnose stream speaks `Worker died.` and a `Fix: Restart it.` line.

- `POST /alerts` returns state `ringing`, one `create_call`, Brief `Worker died.`, Fix `Restart it.`, and an agent id.
- A human voice webhook moves state to `in_call` and returns the fake TwiML.
- First chat completion speaks the Brief and `Anything else?`, arms Execute, sends no SMS, and does not hang up.
- A following user message `no` sends one start Receipt containing `worker died`, does not hang up, and leaves state `in_call`.
- A following user message `check` hangs up once and the last SMS contains `worker died` and `succeeded`. State is `closed`.
- Status `no-answer` sets `text_session` and sends an SMS containing the Brief. A later unknown `CallSid` returns Hangup TwiML. `accept_inbound_call()` is false.
- A second alert while the first is `in_call` returns state `queued` and does not dial. `drop` then promote dials the second Incident and leaves it `ringing`. `drop` itself emits no closing Receipt.

## Done when

`python -m pytest -q` passes, including telephony, state, bridge, agent contract, seam, and wiring. The run uses no API keys.
