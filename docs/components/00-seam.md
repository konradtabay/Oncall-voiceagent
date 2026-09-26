# Agent brief: Seam

You own the messages that cross component boundaries. You do not own behavior.

## Read

- [docs/implementation-steps.md](../implementation-steps.md)
- This file

## Edit only

- `src/oncall/seam.py`
- `tests/test_seam.py`

Do not edit `telephony/`, `incident/`, `app.py`, or `DESIGN.md`.

## What you receive

Nothing. No other component calls into this package except to import the types.

## What you send out

Frozen dataclasses. Other components construct them. They do not subclass them and they do not add fields.

### Commands (incident state emits, telephony performs)

| Type | Fields | Who emits | Who consumes |
| --- | --- | --- | --- |
| `Dial` | `incident_id: str`, `to_number: str` | Incident state `ready_to_dial` | Telephony `dial` |
| `Hangup` | `incident_id: str`, `reason: close \| miss \| drop` | Incident state `on_missed`, `on_phase(verified)`, `on_phase(drop)` | Telephony `hangup` |
| `SmsOut` | `incident_id: str`, `body: str`, `kind: start_receipt \| closing_receipt \| text_turn \| follow_up` | Incident state, and Wiring for a Follow-up answer | Telephony `sms_out` |

### Events (telephony emits, wiring consumes)

| Type | Fields | Who emits | Who consumes |
| --- | --- | --- | --- |
| `Answered` | `incident_id: str`, `call_sid: str` | Telephony voice webhook on a human | Wiring `handle_event` |
| `Missed` | `incident_id: str`, `reason: no-answer \| busy \| failed \| canceled \| machine` | Telephony voice or status webhook | Wiring `handle_event` |
| `SmsIn` | `from_number: str`, `body: str` | Telephony SMS webhook | Wiring `handle_event` |

`Utterance(incident_id, text)` exists so a spoken turn has a type. Wiring builds it from the last user message in `POST /v1/chat/completions`. Telephony never emits it.

`Command` is `Dial | Hangup | SmsOut`. `Event` is `Answered | Missed | SmsIn | Utterance`.

## Handoff rule

If a component needs a new field, it does not get one by editing a sibling. It asks for a seam change first. Until that change lands, the types above are the whole interface.

## Done when

`tests/test_seam.py` constructs one of each type and reads every field. `python -m pytest tests/test_seam.py -q` passes with no network.
