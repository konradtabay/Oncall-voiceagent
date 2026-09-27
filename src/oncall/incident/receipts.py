"""Plain-language receipt text for SMS."""

from __future__ import annotations


def _short(text: str, limit: int = 72) -> str:
    line = " ".join((text or "").split()).strip().rstrip(".")
    if not line:
        return "the incident"
    if len(line) <= limit:
        return line
    cut = line[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(".,;:")


def start_receipt(issue: str, solution: str) -> str:
    """Short notice that a Fix has started. Must name the issue and solution."""
    return f"Fix started.\n{_short(issue)}\n{_short(solution, 90)}"


def closing_receipt(issues: list[dict]) -> str:
    """Closing SMS: every issue, its solution, and that it succeeded."""
    if not issues:
        return "All clear. Every fix succeeded."
    parts = []
    for item in issues:
        issue = item.get("issue", "")
        solution = item.get("solution", "")
        parts.append(f"For {issue}, {solution} — it succeeded.")
    return " ".join(parts)


def text_open(brief: str, fix: str) -> str:
    """SMS that opens a Text Session: brief and the one fix."""
    return f"{brief} Suggested fix: {fix}"
