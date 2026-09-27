"""Voice line compaction and diagnose parsing."""

from oncall.incident.voice import call_opening, split_diagnosis, voice_compact


def test_split_diagnosis_two_lines():
    text = "Brief: Worker died.\nFix: Restart it."
    brief, fix = split_diagnosis(text)
    assert brief == "Worker died."
    assert fix == "Restart it."


def test_split_diagnosis_ignores_markdown_ramble():
    text = (
        "Looking at logs.\n\n"
        "Brief: Your worker process crashed.\n\n"
        "**Next steps:**\n"
        "Fix: Restart the worker and check the health URL."
    )
    brief, fix = split_diagnosis(text)
    assert "worker" in brief.lower()
    assert "restart" in fix.lower()
    assert "next steps" not in brief.lower()
    assert len(brief.split()) <= 28
    assert len(fix.split()) <= 28


def test_call_opening_hey_man_no_brief_word():
    line = call_opening("Worker died.", "Restart it.")
    assert line.lower().startswith("hey.")
    assert "brief" not in line.lower()
    assert "let me know" in line.lower()


def test_voice_compact_first_sentence():
    long = (
        "Your worker stopped. It exited with code one. "
        "The health check is probably failing too."
    )
    short = voice_compact(long)
    assert short.endswith(".")
    assert "health check" not in short
