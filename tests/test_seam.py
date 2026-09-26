from oncall.seam import Answered, Dial, Hangup, Missed, SmsIn, SmsOut, Utterance


def test_commands_and_events_are_frozen_payloads():
    dial = Dial("inc-1", "+15555550100")
    hangup = Hangup("inc-1", "close")
    sms = SmsOut("inc-1", "The process is back.", "closing_receipt")
    answered = Answered("inc-1", "CA123")
    missed = Missed("inc-1", "machine")
    inbound = SmsIn("+15555550100", "send the error log")
    said = Utterance("inc-1", "do it")

    assert dial.to_number.startswith("+")
    assert hangup.reason == "close"
    assert sms.kind == "closing_receipt"
    assert answered.call_sid == "CA123"
    assert missed.reason == "machine"
    assert inbound.body == "send the error log"
    assert said.text == "do it"
