"""Spoken-line shaping for phone and ElevenLabs (not the word 'brief' on calls)."""

from __future__ import annotations

import re

_BRIEF_LINE = re.compile(r"^Brief:\s*(.+)$", re.I | re.M)
_FIX_LINE = re.compile(r"^Fix:\s*(.+)$", re.I | re.M)


def plain_speech(text: str) -> str:
    cleaned = text.replace("**", "").replace("*", "").replace("`", "")
    cleaned = re.sub(r"^#+\s*", "", cleaned, flags=re.M)
    while "\n\n" in cleaned:
        cleaned = cleaned.replace("\n\n", "\n")
    return cleaned.strip()


def voice_agent(text: str, *, max_chars: int = 1200) -> str:
    """Longer context for the ElevenLabs agent (Q&A on the call)."""
    line = plain_speech(text).strip().replace("\n", " ")
    if len(line) <= max_chars:
        return line
    return line[: max_chars - 1].rsplit(" ", 1)[0] + "."


def voice_compact(text: str, *, max_words: int = 28, max_chars: int = 180) -> str:
    """One short spoken sentence for the call."""
    line = plain_speech(text).strip()
    for prefix in ("brief:", "fix:"):
        if line.lower().startswith(prefix):
            line = line[len(prefix) :].strip()
    line = line.replace("\n", " ").strip()
    if not line:
        return ""
    # First sentence only when the model still rambles.
    match = re.search(r"^(.+?[.!?])(?:\s|$)", line)
    if match and len(match.group(1)) < max_chars:
        line = match.group(1).strip()
    words = line.split()
    if len(words) > max_words:
        line = " ".join(words[:max_words]).rstrip(",;:") + "."
    if len(line) > max_chars:
        line = line[: max_chars - 1].rsplit(" ", 1)[0] + "."
    return line


def split_diagnosis(text: str) -> tuple[str, str]:
    """Parse diagnose output into short spoken issue + fix lines."""
    cleaned = plain_speech(text.replace("Still working.", ""))
    brief_m = _BRIEF_LINE.search(cleaned)
    fix_m = _FIX_LINE.search(cleaned)
    if brief_m and fix_m:
        return voice_compact(brief_m.group(1)), voice_compact(fix_m.group(1))
    if "Fix:" in cleaned:
        left, right = cleaned.split("Fix:", 1)
        return voice_compact(left), voice_compact(right)
    compact = voice_compact(cleaned)
    return compact, compact


CLOSING_CTA = "Let me know."
KEEP_UPDATED = "I'll keep you updated."


def call_opening(issue: str, fix: str) -> str:
    issue_line = voice_compact(issue) or "Something broke."
    fix_line = voice_compact(fix) or "Restart it."
    return f"Hey. {issue_line} The fix is {fix_line}. {CLOSING_CTA}"
