"""Demo terminal: pause, red logs, dial, green fix, spoken success."""

import time


def test_demo_page_and_scripted_success(tmp_path):
    from tests.test_wiring import _world

    service, twilio, telephony, client = _world(tmp_path)
    service._cursor_async = False
    service._demo_break_delay = 0
    service._demo_error_step = 0
    service._demo_keep_updated_delay = 0.12
    service._demo_success_delay = 0
    service._demo_fix_step = 0

    page = client.get("/demo")
    assert page.status_code == 200
    assert "Run the incident?" in page.text
    assert ">Run</button>" in page.text or 'class="run"' in page.text
    assert 'id="launcher"' in page.text
    assert 'id="textDrop"' in page.text
    assert ">healthy</button>" not in page.text.lower()
    assert "Run it" not in page.text
    assert client.get("/demo/state").json()["stage"] == "healthy"

    started = client.post("/demo/run", json={"to_number": "+15555550100"})
    assert started.status_code == 200
    assert service.demo.stage() == "error"
    assert "WRONGTYPE" in " ".join(line["text"] for line in service.demo.lines())
    assert all(line["alert"] for line in service.demo.lines())
    assert twilio.calls == ["CA1"]
    assert service.cursor.runs == []

    incident_id = service.store.active().id
    ctx = service.call_context(incident_id)
    assert "training:encode:cursor" in ctx["brief"]
    assert "XGROUP" in ctx["fix"] or "DEL" in ctx["fix"]
    assert "LatticeTrain" in ctx["project"]
    assert "Northern Lattice" in ctx["project"]
    assert "Canadian" in ctx["project"]
    telephony.handle_voice(
        {
            "CallSid": "CA1",
            "AnsweredBy": "human",
            "From": "+15550001111",
            "To": "+15555550100",
        },
        True,
    )
    phase = client.post(
        "/elevenlabs/phase",
        json={"value": "execute", "incident_id": incident_id},
    )
    assert phase.status_code == 200
    body = phase.json()["result"].lower()
    assert "keep you updated" in body
    assert "health is back" not in body
    assert service.demo.stage() == "error"
    texts = client.get("/demo/state").json()["messages"]
    assert texts
    assert texts[0]["kind"] == "start_receipt"
    assert texts[0]["body"] == (
        "Fix started.\ntrain-runner is down\nDelete the bad Redis key and restart it"
    )

    deadline = time.time() + 2.0
    while time.time() < deadline and service.demo.stage() != "success":
        time.sleep(0.02)
    assert service.demo.stage() == "success"

    spoken = client.post(
        "/elevenlabs/updates",
        json={"incident_id": incident_id},
    ).json()
    assert spoken["update"] == "Fix complete, health is back. Chat soon."
    again = client.post(
        "/elevenlabs/updates",
        json={"incident_id": "unknown"},
    ).json()
    assert "fix complete" in again["update"].lower()
    assert twilio.hungup == []
    assert service.store.get(incident_id).state == "in_call"
    assert service.cursor.runs == []
