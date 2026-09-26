# Agent brief: Incident state

You are the pure loop. You store the Incident, apply phase rules, and return seam commands. You do not call Twilio, ElevenLabs, or Cursor.

## Read

- [docs/implementation-steps.md](../implementation-steps.md)
- [docs/components/00-seam.md](00-seam.md)
- `src/oncall/seam.py`
- This file

## Edit only

- `src/oncall/incident/models.py`
- `src/oncall/incident/store.py`
- `src/oncall/incident/machine.py`
- `src/oncall/incident/receipts.py`
- `src/oncall/incident/__init__.py`
- `tests/test_state_machine.py`

Do not create or edit `cursor_client.py`, `bridge.py`, `prompts.py`, `guard.py`, `service.py`, `app.py`, or `telephony/`. Do not import `twilio` or `httpx`.

## Handoffs

### You receive

| Input | From | What you do |
| --- | --- | --- |
| `Incident` | Wiring `open_alert` | `open_or_queue` |
| `brief`, `fix` strings | Wiring, after the diagnose run | `ready_to_dial` |
| `Answered` fields | Wiring | `on_answered(incident_id, call_sid)` |
| `Missed` fields | Wiring | `on_missed(incident_id, reason)` |
| phase value, optional issue, optional solution | Wiring, from the bridge callback | `on_phase(incident_id, phase, issue, solution)` |
| SMS body | Wiring | `on_sms(incident_id, body)` |

You never see Twilio form fields or Cursor SSE.

### You send

Every method returns `list[Command]` except `on_sms` and `promote_queue`.

| Method | Returns | Commands inside |
| --- | --- | --- |
| `open_or_queue` | `[]` | none. Either save state `diagnosing`, or enqueue and do not insert an active row. |
| `ready_to_dial` | one command | `Dial(incident_id, to_number)`. State becomes `ringing`. |
| `on_answered` | `[]` | State becomes `in_call`. Store `call_sid`. |
| `on_missed` | two commands, only from `ringing` | `Hangup(id, "miss")`, then `SmsOut(id, text_open(brief, fix), "text_turn")`. State becomes `text_session`. If already `text_session` or not `ringing`, return `[]`. |
| `on_phase` | see phase rules | `SmsOut` and sometimes `Hangup` |
| `on_sms` | `(classification, commands)` | classification is `"turn"` or `"follow_up"`. Commands are `[]`. Follow-up text is stored on the turn queue. |
| `accept_inbound_call` | `False` | always |
| `promote_queue` | `Incident \| None` | If an Incident is still active, return `None`. Otherwise pop the oldest queued alert, save it as `diagnosing`, and return it. |

Wiring is responsible for performing `Dial`, `Hangup`, and `SmsOut`. You only return them.

## Models

```text
Incident:
  id, state, to_number, summary, logs, verify_target, brief, fix
  armed: bool = False
  fixing: bool = False
  agent_id: str = ""
  call_sid: str = ""
  run_locked: bool = False
  issues: list[dict]   # {issue, solution, success}

QueuedAlert:
  id, summary, logs, verify_target, to_number, created_order
```

States: `diagnosing`, `ringing`, `in_call`, `text_session`, `closed`, `dropped`, `queued`.

## Store

SQLite, stdlib `sqlite3`. Tables: `incidents` (issues as JSON), `queued_alerts`, `turn_queue`.

```text
insert_incident, get, save, active, enqueue, pop_next
set_run_lock(incident_id, locked)
enqueue_turn(incident_id, text)
pop_turn(incident_id) -> str | None
latest_for_number(to_number) -> Incident | None
```

`active` is the one row whose state is not `queued`, `closed`, or `dropped`. `enqueue` assigns `created_order` when the caller passes `0`. `pop_next` returns the oldest and deletes it. `latest_for_number` prefers `in_call`, then `text_session`, then `ringing`, then `diagnosing`, then the newest row.

## Phase rules

`phase(talking)`: if `armed`, clear it. No commands.

`phase(execute)` while not armed: set `armed`. No commands. No Receipt.

`phase(execute)` while armed: clear `armed`, set `fixing`, append `{issue: issue or fix, solution: solution or fix, success: False}`. Return one `SmsOut` kind `start_receipt`. Do not return `Hangup`. Stay in `in_call` or `text_session`.

`phase(verified)`: set every issue `success` true. If state is `in_call`, include `Hangup(id, "close")`. Always include `SmsOut` kind `closing_receipt`. State `closed`. Clear `armed` and `fixing`.

`phase(failed)`: clear `armed` and `fixing`. Stay in the current session. No `Hangup`. No closing Receipt. If `issue` was passed, it replaces `brief`. If `solution` was passed, it replaces `fix`.

`phase(drop)`: state `dropped`. Clear `armed` and `fixing`. Include `Hangup(id, "drop")` when the prior state was `in_call` or `ringing`, or `text_session` with a `call_sid`. No closing Receipt.

## Receipt text

```text
start_receipt(issue, solution) -> str
  Contains the issue and the solution. Short. No stack trace.

closing_receipt(issues) -> str
  For each issue: the issue, the solution, and the word "succeeded".

text_open(brief, fix) -> str
  The Brief and the one Fix, for the SMS that opens a Text Session.
```

`__init__.py` exports `Machine`, `Store`, `Incident`, `start_receipt`, `closing_receipt`.

## Tests

`tests/test_state_machine.py` uses a temp SQLite file. No network.

- `execute` then `talking` emits no start Receipt and `armed` is false.
- `execute` then `execute` emits one start Receipt and no `Hangup`. State stays `in_call`.
- `failed` from `in_call` stays `in_call`, emits no closing Receipt, `armed` is false.
- `verified` emits `Hangup` reason `close` and a closing Receipt that names every issue and contains `succeeded`. State is `closed`.
- `on_missed` from `ringing` sets `text_session`, emits `Hangup` reason `miss`, and emits `text_turn` containing the Brief.
- `accept_inbound_call()` is false.
- A start Receipt does not set state `text_session`.
- `on_sms` during `in_call` returns `follow_up`, enqueues the body, and does not change state.
- A second Incident while one is active is queued. After `verified` or `drop`, `promote_queue` returns it in `diagnosing`, oldest first.
- `drop` from `in_call` emits `Hangup` reason `drop` and no closing Receipt.

## Done when

`python -m pytest tests/test_state_machine.py tests/test_seam.py -q` passes. `machine.py` imports only models, store, receipts, and `oncall.seam`.
