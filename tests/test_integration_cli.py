"""CLI quickstart and integration snippets."""

from __future__ import annotations

import pytest

from oncall.cli import main
from oncall.integration import agent_quickstart_prompt, human_quickstart


def test_human_quickstart_mentions_voice_sync():
    text = human_quickstart()
    assert "oncall voice sync" in text
    assert "oncall agent quickstart" in text


def test_agent_prompt_includes_alerts_and_repo():
    text = agent_quickstart_prompt()
    assert "/alerts" in text
    assert "REPO_URL" in text
    assert "oncall check" in text


def test_cli_quickstart_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["quickstart"])
    assert exc.value.code == 0
    assert "quick start" in capsys.readouterr().out.lower()


def test_cli_agent_quickstart_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["agent", "quickstart"])
    assert exc.value.code == 0
    assert "Integrate on-call voice" in capsys.readouterr().out
