#!/usr/bin/env python3
"""Text-only incident dry run: no phone, Twilio, Cursor, or ElevenLabs network calls.

Uses the same fakes as tests/test_wiring.py. Prints agent speech (SSE) and SMS.

  source .venv/bin/activate
  python3 scripts/simulate_incident.py           # scripted demo
  python3 scripts/simulate_incident.py -i      # type user lines; empty line to quit

  # or without activate:
  .venv/bin/python3 scripts/simulate_incident.py
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from tests.test_wiring import _world  # noqa: E402


def sse_to_text(body: str) -> str:
    parts: list[str] = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if payload == "[DONE]":
            continue
        data = json.loads(payload)
        delta = (data.get("choices") or [{}])[0].get("delta") or {}
        chunk = delta.get("content")
        if chunk:
            parts.append(str(chunk))
    return "".join(parts)


def chat(client, messages: list[dict]) -> str:
    response = client.post("/v1/chat/completions", json={"messages": messages})
    response.raise_for_status()
    return sse_to_text(response.text)


def print_sms(twilio, seen: int) -> int:
    while seen < len(twilio.sms):
        print(f"\n[SMS]\n{twilio.sms[seen]}\n")
        seen += 1
    return seen


def run_scripted(client, telephony, twilio) -> None:
    incident_id = "sim-incident"
    client.post(
        "/alerts",
        json={
            "summary": "worker down",
            "logs": "exit 1",
            "verify_target": "http://health",
            "to_number": "+15555550100",
            "incident_id": incident_id,
        },
    )
    telephony.handle_voice(
        {
            "CallSid": "CA1",
            "AnsweredBy": "human",
            "From": "+15550001111",
            "To": "+15555550100",
        },
        True,
    )
    sms_seen = 0
    turns = [
        ("(opening)", []),
        ("user: do it", [{"role": "user", "content": "do it"}]),
        ("user: no", [{"role": "user", "content": "no"}]),
        ("user: check", [{"role": "user", "content": "check"}]),
    ]
    for label, messages in turns:
        spoken = chat(client, messages)
        print(f"\n[{label}]\n{spoken or '(no speech)'}\n")
        sms_seen = print_sms(twilio, sms_seen)


def run_interactive(client, telephony, twilio) -> None:
    incident_id = "sim-incident"
    client.post(
        "/alerts",
        json={
            "summary": "worker down",
            "logs": "exit 1",
            "verify_target": "http://health",
            "to_number": "+15555550100",
            "incident_id": incident_id,
        },
    )
    telephony.handle_voice(
        {
            "CallSid": "CA1",
            "AnsweredBy": "human",
            "From": "+15550001111",
            "To": "+15555550100",
        },
        True,
    )
    sms_seen = 0
    spoken = chat(client, [])
    print(f"\n[agent]\n{spoken}\n")
    sms_seen = print_sms(twilio, sms_seen)
    print("Type what you would say on the call (empty line to exit).\n")
    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            break
        spoken = chat(client, [{"role": "user", "content": line}])
        print(f"\n[agent]\n{spoken or '(no speech)'}\n")
        sms_seen = print_sms(twilio, sms_seen)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Type user lines instead of running the canned demo",
    )
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        _service, twilio, telephony, client = _world(Path(tmp))
        if args.interactive:
            run_interactive(client, telephony, twilio)
        else:
            run_scripted(client, telephony, twilio)
        if twilio.hungup:
            print(f"[call ended: hangup {twilio.hungup}]")


if __name__ == "__main__":
    main()
