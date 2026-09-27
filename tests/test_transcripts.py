"""Transcript parsing and persistence."""

from oncall.incident.store import Store
from oncall.incident.transcripts import conversation_id_from_twiml, format_transcript_text
from oncall.telephony.service import conversation_id_from_twiml as from_service


def test_conversation_id_from_register_twiml():
    twiml = (
        '<?xml version="1.0"?><Response><Connect><Stream url="wss://x">'
        '<Parameter name="conversation_id" value="conv_abc123" /></Stream></Connect></Response>'
    )
    assert conversation_id_from_twiml(twiml) == "conv_abc123"
    assert from_service(twiml) == "conv_abc123"


def test_format_transcript_text():
    detail = {
        "transcript": [
            {"role": "agent", "message": "Hi"},
            {"role": "user", "message": "Go ahead"},
        ]
    }
    text = format_transcript_text(detail)
    assert "[agent] Hi" in text
    assert "[user] Go ahead" in text


def test_store_call_transcript(tmp_path):
    store = Store(str(tmp_path / "t.sqlite3"))
    store.save_call_transcript(
        "inc-1",
        "conv_x",
        "summary",
        "[user] hello",
        "[]",
    )
    row = store.get_call_transcript("inc-1")
    assert row is not None
    assert row["transcript_text"] == "[user] hello"
