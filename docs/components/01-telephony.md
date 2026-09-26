# Agent brief: Telephony

You place the call, detect a Miss, hand a human answer to ElevenLabs, hang up when told, and send SMS. You do not decide Execute, Verify, Receipt text, or whether an SMS is a Text Session or a Follow-up.

## Read

- [docs/implementation-steps.md](../implementation-steps.md)
- [docs/components/00-seam.md](00-seam.md)
- `src/oncall/seam.py`
- This file

## Edit only

- `src/oncall/telephony/**`
- `tests/test_telephony.py`

Do not edit `src/oncall/incident/`, `src/oncall/app.py`, `src/oncall/seam.py`, or `DESIGN.md`.

## Handoffs

### You receive

| Input | From | Shape |
| --- | --- | --- |
| `Dial` | Wiring, after diagnosis | `Dial(incident_id, to_number)` |
| `Hangup` | Wiring, from incident state | `Hangup(incident_id, reason)` where reason is `close`, `miss`, or `drop` |
| `SmsOut` | Wiring | `SmsOut(incident_id, body, kind)`. Send `body`. Ignore `kind` for routing. |
| Voice webhook | Twilio | form fields `CallSid`, `AnsweredBy`, `CallStatus`, `From`, `To`. Query may include `incident_id`. |
| Status webhook | Twilio | form fields `CallSid`, `CallStatus`, `AnsweredBy`. Query may include `incident_id`. |
| SMS webhook | Twilio | form fields `From`, `Body` |
| Signature | Twilio | header `X-Twilio-Signature` |

`on_event` is injected at construction. You call it. You do not import Wiring or the state machine.

```text
on_event(event: Answered | Missed | SmsIn) -> str | None
```

For `SmsIn`, the return value is an optional TwiML `<Message>` body. `None` means an empty `<Response>`. Conversational replies are sent by Wiring through `sms_out`, so `on_event` usually returns `None`.

### You send

| Output | To | When |
| --- | --- | --- |
| `Answered(incident_id, call_sid)` | `on_event` | Human answered. After `register_call`. |
| `Missed(incident_id, reason)` | `on_event` | Machine, no-answer, busy, failed, or canceled. |
| `SmsIn(from_number, body)` | `on_event` | Every valid inbound SMS. |
| TwiML from `register_call` | Twilio voice webhook | Human answer only. |
| `<Response><Hangup/></Response>` | Twilio voice webhook | Miss, or any inbound call you did not dial. |
| REST `calls.create` | Twilio | `dial` |
| REST hangup | Twilio | `hangup` when you still have that call sid |
| REST `messages.create` | Twilio | `sms_out` |

## Public API you must provide

```text
class TwilioPort:
    create_call(to, from_, voice_url, status_url) -> call_sid
    hangup(call_sid) -> None
    send_sms(to, from_, body) -> None

class ElevenLabsPort:
    register_call(incident_id, from_number, to_number) -> twiml_str

class Telephony:
    __init__(twilio_port, elevenlabs_port, validator, on_event, *, from_number="", voice_url="", status_url="")
    dial(command: Dial) -> call_sid
    hangup(command: Hangup) -> None
    sms_out(command: SmsOut) -> None
    handle_voice(form: dict, signature_ok: bool) -> Response
    handle_status(form: dict, signature_ok: bool) -> None
    handle_sms(form: dict, signature_ok: bool) -> str | None

signature_ok(url, params, signature, token) -> bool
reject_bad_signature() -> Response  # status 403
router  # POST /twilio/voice, /twilio/status, /twilio/sms
bind(telephony, auth_token=None)
```

The real Twilio adapter's `create_call` passes answering-machine detection (`MachineDetection=Enable`). Tests use a fake port and must not construct the real adapter.

## Behavior

1. `dial` calls `create_call` once. Remember `call_sid -> incident_id` and `incident_id -> to_number`. Append `incident_id` to the voice and status URLs.
2. Voice webhook, known call, `AnsweredBy` starts with `machine`, or `CallStatus` in `no-answer | busy | failed | canceled`: emit `Missed`, return Hangup TwiML, do not call `register_call`. Machine reason is `machine`. Other miss reasons are the status string.
3. Voice webhook, known call, `AnsweredBy=human` or `CallStatus` in `in-progress | answered`: call `register_call`, emit `Answered`, return that TwiML.
4. Voice webhook, unknown `CallSid`: if the form has `incident_id` for a call you dialed, treat it as that call. Otherwise return Hangup TwiML and do not emit `Answered` and do not register. This is the ignored callback.
5. Status webhook: same Miss mapping. `completed` emits nothing.
6. `hangup` calls the port only for reasons `close`, `miss`, and `drop`, and only if you still have the call sid. It does not send SMS.
7. `sms_out` sends `body` to the number remembered at `dial`. It does not hang up and it does not change call state.
8. `handle_sms` emits `SmsIn` and returns whatever `on_event` returns. You do not classify the text.
9. A bad signature is HTTP 403. `signature_ok` is false when a token is set and `RequestValidator` fails. An empty token skips the check so tests can pass `signature_ok` themselves.

## Tests

`tests/test_telephony.py`, fakes only:

- Human answer emits `Answered`, calls `register_call` once, and returns that TwiML.
- `AnsweredBy=machine_start` emits `Missed(reason=machine)`, returns Hangup TwiML, and does not register.
- Status `no-answer`, `busy`, `failed`, `canceled` each emit `Missed` with that reason.
- Status `completed` emits nothing.
- A bad signature is 403.
- `sms_out` does not hang up.
- `hangup(reason=close)` hangs up once.
- An unknown `CallSid` returns Hangup and does not register.
- `handle_sms` emits `SmsIn` and returns the string `on_event` returned.

## Done when

`python -m pytest tests/test_telephony.py tests/test_seam.py -q` passes. You did not import `oncall.incident`.
