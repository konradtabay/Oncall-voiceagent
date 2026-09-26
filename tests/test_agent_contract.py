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


def test_deploy_guard_single_execute_refuses():
    guard = DeployGuard()
    guard.on_phase("execute")
    assert guard.allow_tool("restart") is False
    guard.on_phase("talking")
    assert guard.allow_tool("deploy") is False


def test_deploy_guard_confirmed_execute_allows():
    guard = DeployGuard()
    guard.on_phase("execute")
    guard.on_phase("execute")
    assert guard.allow_tool("ssh") is True
    assert guard.allow_tool("ssh") is True
    assert guard.allow_tool("ssh") is True
    # Scripted runner would invoke the tool once; allow stays true after start.
    invoke_count = 0
    if guard.allow_tool("ssh"):
        invoke_count += 1
    assert invoke_count == 1
    assert guard.fix_started is True


def test_diagnose_script_no_deploy():
    guard = DeployGuard()
    deployed = run_script(guard, [("tool", "deploy")])
    assert deployed == []


def test_execute_then_talking_refuses_deploy():
    guard = DeployGuard()
    deployed = run_script(
        guard,
        [("phase", "execute"), ("phase", "talking"), ("tool", "deploy")],
    )
    assert deployed == []


def test_confirmed_execute_allows_deploy_once():
    guard = DeployGuard()
    deployed = run_script(
        guard,
        [
            ("phase", "execute"),
            ("phase", "execute"),
            ("tool", "deploy"),
        ],
    )
    assert deployed == ["deploy"]


def test_failed_refuses_until_new_confirmed_execute():
    guard = DeployGuard()
    first = run_script(
        guard,
        [
            ("phase", "execute"),
            ("phase", "execute"),
            ("tool", "deploy"),
            ("phase", "failed"),
            ("tool", "restart"),
        ],
    )
    assert first == ["deploy"]

    second = run_script(
        guard,
        [
            ("phase", "execute"),
            ("phase", "execute"),
            ("tool", "restart"),
        ],
    )
    assert second == ["restart"]
