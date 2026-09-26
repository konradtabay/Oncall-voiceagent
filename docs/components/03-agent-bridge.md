# Agent brief: Agent bridge

You talk to the Cursor cloud agent and turn its stream into spoken text plus phase events. You do not store Incidents, place calls, or send SMS.

## Read

- [docs/implementation-steps.md](../implementation-steps.md)
- This file

## Edit only

- `src/oncall/incident/cursor_client.py`
- `src/oncall/incident/bridge.py`
- `src/oncall/incident/prompts.py`
- `src/oncall/incident/guard.py`
- `tests/test_bridge.py`
- `tests/test_agent_contract.py`
- `tests/fixtures/cursor_run.sse`
- `fixtures/staging/process.py`
- `fixtures/staging/README.md`

Do not edit `incident/__init__.py`, `models.py`, `store.py`, `machine.py`, `receipts.py`, `service.py`, or `telephony/`. Do not import the state machine.

## Handoffs

### You receive

| Input | From | Shape |
| --- | --- | --- |
| Create-agent request | Wiring | `repo_url: str`, `prompt: str`, `env: dict \| None` |
| Follow-up text | Wiring | `agent_id: str`, `text: str` |
| SSE lines | `CursorClient.stream` | `event:` / `data:` blocks, `data` is JSON |
| Phase callback | Wiring supplies it | `on_phase(value: str, issue: str, solution: str) -> None` |

You do not know call state. Wiring applies your phase callback to the state machine.

### You send

| Output | To | Shape |
| --- | --- | --- |
| Agent id | Wiring | `str` from `create_agent` |
| Run id | Wiring | `str` from `create_run` |
| Spoken chunks | Wiring, which streams them to ElevenLabs | `Iterator[str]` from `Bridge.consume` |
| Phase notification | Wiring's callback | `on_phase("execute" \| "talking" \| "verified" \| "failed" \| "drop", issue, solution)` |
| Allow or refuse | Wiring, or a scripted test | `DeployGuard.allow_tool(name) -> bool` |

Spoken chunks are the only words that may be heard. Phase arguments are not spoken.

## Cursor client

```text
class CursorClient:
    create_agent(repo_url, prompt, env=None) -> agent_id
    create_run(agent_id, text) -> run_id
    stream(agent_id, run_id) -> Iterator[str]   # raw SSE lines

class HttpCursorClient(CursorClient):
    base https://api.cursor.com
    Authorization: Bearer <api_key>
    also HTTP basic auth (api_key, "")
    POST /v1/agents
      body: {"prompt": {"text": prompt}, "repos": [{"url": repo_url}], "env": env?}
      id from response id, agent_id, or agent.id
    POST /v1/agents/{id}/runs
      body: {"prompt": {"text": text}}
      id from response id, run_id, or run.id
      HTTP 409 whose body contains agent_busy: sleep and retry, up to 5 times
    GET /v1/agents/{id}/runs/{run_id}/stream
      yield each line
```

Tests inject a fake. They must not call `HttpCursorClient`. `sleep` and `busy_wait` are constructor arguments so a test can retry without waiting.

## Bridge

```text
STILL_WORKING = "Still working."

parse_sse(lines) -> Iterator[{event, data}]
Bridge(on_phase=None).consume(lines) -> Iterator[str]
```

- `event: assistant` with `data.text`: yield that text immediately, one yield per event. Do not buffer the run.
- `event: thinking`: yield nothing.
- `event: tool_call` name `phase` and status `completed` or `complete`: call `on_phase(args.value, args.issue, args.solution)`. Do not yield the tool name or the arguments.
- `event: tool_call` any other name and status `started`, `running`, or `in_progress`: yield `Still working.` once per `callId`.
- Anything else: ignore.

`args` may arrive as `args` or `arguments`. `callId` may arrive as `callId`, `call_id`, or `id`.

## Prompt and phase tool

`AGENT_PROMPT` is one short string. It must say: phone call with the Maintainer; plain language a fifteen-year-old follows; one Fix; do not change the server until the Maintainer has said to do it and then said there is nothing else; call the phase tool; after a Fix, check the verify target before saying the process is back.

`DIAGNOSE_INSTRUCTION` must tell the agent to write a Brief and one Fix and not change the server. Wiring tells the diagnose run to end with a line that starts `Fix: `.

`PHASE_TOOL` is a JSON schema named `phase`. Required argument `value` is the enum `talking | execute | verified | failed | drop`. Optional `issue` and `solution` strings.

## Deploy guard

This is the policy Wiring and the contract tests consult. It does not cancel a live cloud-agent tool. It answers whether that tool should have been allowed.

```text
class DeployGuard:
    fix_started: bool
    armed: bool
    on_phase(value: str) -> None
    allow_tool(name: str) -> bool
```

`allow_tool` returns True unless the lowercased name contains `deploy`, `ssh`, or `restart`. Those return True only when `fix_started` is True.

`on_phase("execute")` while not armed: arm. `fix_started` stays false.
`on_phase("execute")` while armed: `fix_started = True`, clear the arm.
`on_phase("talking" | "failed" | "verified" | "drop")`: clear the arm. `failed`, `verified`, and `drop` also set `fix_started` false.

So: diagnose refuses deploy. Execute then talking refuses deploy. Execute then execute allows deploy. Failed verify refuses deploy until another confirmed execute.

## Staging fixture

`fixtures/staging/process.py` with commands `start`, `kill`, `restart`, `status`. Default health file `fixtures/staging/health`. `start` and `restart` write `up`. `kill` deletes the file. `status` prints `up` or `down` and exits 0 only when up.

`fixtures/staging/README.md` describes two manual calls. Do not place them from pytest.

1. Answer, say to execute, stay on the line, hear Verify, receive the closing Receipt, then text `send the error log`.
2. Decline the call and finish the same Incident by SMS.

## Tests

`tests/fixtures/cursor_run.sse` contains, in order: a status event, assistant text `The worker died. `, a thinking event whose text is `secret-chain-of-thought`, assistant text `I would restart it.`, a started `deploy` tool call, and a completed `phase` tool call with value `execute`, issue `worker died`, solution `restart it`.

`tests/test_bridge.py`:

- The first `next()` of `consume` is exactly `The worker died. `.
- Spoken output contains that sentence, `Still working.`, and `I would restart it.`
- Spoken output does not contain `secret-chain-of-thought` or the raw tool arguments.
- `on_phase` is called once with `("execute", "worker died", "restart it")`.

`tests/test_agent_contract.py` uses a scripted runner, not HTTP:

- `DIAGNOSE_INSTRUCTION` says not to change the server.
- One `execute` then `allow_tool("restart")` is false.
- `execute` then `talking` then `deploy` is not invoked.
- `execute` then `execute` then `deploy` invokes `deploy` once.
- After `failed`, `restart` is not invoked.
- A later `execute` then `execute` allows `restart`.

## Done when

`python -m pytest tests/test_bridge.py tests/test_agent_contract.py tests/test_seam.py -q` passes. `python fixtures/staging/process.py start` prints a healthy status, and `kill` makes `status` exit non-zero.
