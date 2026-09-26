"""Bridge SSE parsing and speech filter tests."""

from __future__ import annotations

from pathlib import Path

from oncall.incident.bridge import Bridge, STILL_WORKING, parse_sse

FIXTURE = Path(__file__).parent / "fixtures" / "cursor_run.sse"


class FakeCursor:
    """Test double; never touches HttpCursorClient."""

    def __init__(self, lines: list[str] | None = None) -> None:
        self._lines = lines or FIXTURE.read_text(encoding="utf-8").splitlines(keepends=True)

    def create_agent(self, repo_url: str, prompt: str, env: dict | None = None) -> str:
        return "agent-fake"

    def create_run(self, agent_id: str, text: str) -> str:
        return "run-fake"

    def stream(self, agent_id: str, run_id: str):
        yield from self._lines


def test_consume_spoken_order_and_phase():
    phases: list[tuple[str, str, str]] = []

    def on_phase(value: str, issue: str, solution: str) -> None:
        phases.append((value, issue, solution))

    bridge = Bridge(on_phase=on_phase)
    lines = FIXTURE.read_text(encoding="utf-8").splitlines(keepends=True)
    spoken = list(bridge.consume(lines))

    joined = "".join(spoken)
    assert spoken[0] == "The worker died. "
    assert STILL_WORKING in spoken
    assert "I would restart it." in spoken
    assert "secret-chain-of-thought" not in joined
    assert '{"cmd": "restart"}' not in spoken
    assert '{"cmd":"restart"}' not in spoken
    for chunk in spoken:
        assert "cmd" not in chunk or chunk == STILL_WORKING
        assert chunk != '{"cmd": "restart"}'
        assert "restart" not in chunk or chunk == "I would restart it."
    # Natural stream order: assistants then Still working; either Still working
    # placement relative to the second assistant is acceptable.
    assert joined == "The worker died. Still working.I would restart it." or joined == (
        "The worker died. I would restart it." + STILL_WORKING
    )
    assert phases == [("execute", "worker died", "restart it")]


def test_first_yield_before_rest_of_stream():
    """consume is a generator; first next() is the first assistant delta."""

    def blocking_lines():
        yield "event: assistant\n"
        yield 'data: {"text": "The worker died. "}\n'
        yield "\n"
        # If consume buffered the whole stream, it would hang waiting here.
        yield "event: thinking\n"
        yield 'data: {"text": "secret-chain-of-thought"}\n'
        yield "\n"
        raise AssertionError("must not pull thinking before first yield is taken")

    bridge = Bridge()
    gen = bridge.consume(blocking_lines())
    first = next(gen)
    assert first == "The worker died. "


def test_parse_sse_event_data_pairs():
    lines = [
        "event: assistant\n",
        'data: {"text": "hi"}\n',
        "\n",
    ]
    items = list(parse_sse(lines))
    assert items == [{"event": "assistant", "data": {"text": "hi"}}]


def test_fake_cursor_feeds_bridge():
    fake = FakeCursor()
    spoken = list(Bridge().consume(fake.stream("a", "r")))
    assert spoken[0] == "The worker died. "
    assert STILL_WORKING in spoken
