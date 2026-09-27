"""Scripted agent-contract tests (no network)."""

from __future__ import annotations

from oncall.incident.guard import DeployGuard
from oncall.incident.prompts import DIAGNOSE_INSTRUCTION


def run_script(guard: DeployGuard, events: list[tuple[str, str]]) -> list[str]:
    """Scripted runner: ("phase", value) or ("tool", name)."""
    invoked: list[str] = []
    for kind, name in events:
        if kind == "phase":
            guard.on_phase(name)
        elif kind == "tool":
            if guard.allow_tool(name):
                invoked.append(name)
    return invoked


def test_diagnose_instruction_forbids_server_change():
    lower = DIAGNOSE_INSTRUCTION.lower()
    assert "not" in lower and "server" in lower or "do not change" in lower
    assert "do not change" in lower or ("not" in lower and "server" in lower)


def test_deploy_guard_before_execute_refuses():
    guard = DeployGuard()
    assert guard.allow_tool("restart") is False
    guard.on_phase("talking")
    assert guard.allow_tool("deploy") is False


def test_deploy_guard_execute_allows_deploy():
    guard = DeployGuard()
    guard.on_phase("execute")
    assert guard.allow_tool("ssh") is True
    assert guard.fix_started is True


def test_diagnose_script_no_deploy():
    guard = DeployGuard()
    deployed = run_script(guard, [("tool", "deploy")])
    assert deployed == []


def test_execute_then_talking_still_allows_deploy():
    guard = DeployGuard()
    deployed = run_script(
        guard,
        [("phase", "execute"), ("phase", "talking"), ("tool", "deploy")],
    )
    assert deployed == ["deploy"]


def test_execute_allows_deploy_once():
    guard = DeployGuard()
    deployed = run_script(
        guard,
        [
            ("phase", "execute"),
            ("tool", "deploy"),
        ],
    )
    assert deployed == ["deploy"]


def test_failed_refuses_until_new_execute():
    guard = DeployGuard()
    first = run_script(
        guard,
        [
            ("phase", "execute"),
            ("tool", "deploy"),
            ("phase", "failed"),
            ("tool", "deploy"),
        ],
    )
    assert first == ["deploy"]
    second = run_script(guard, [("phase", "execute"), ("tool", "restart")])
    assert second == ["restart"]
