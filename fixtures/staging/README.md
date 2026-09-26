# Staging fixture (manual)

This folder is for a live staging call. It is **not** run by pytest.

## Health process

```bash
python fixtures/staging/process.py start    # writes health file "up"
python fixtures/staging/process.py status   # prints up/down; exit 1 if down
python fixtures/staging/process.py kill     # removes health file
python fixtures/staging/process.py restart  # writes "up" again
```

Default health path: `fixtures/staging/health`.

## Path 1 — answer and Fix

1. Place a real Twilio outbound call to the Maintainer.
2. Answer the call.
3. Say execute (confirm: ask to do it, then say there is nothing else).
4. Stay on the line while the Fix runs.
5. Verify (agent checks the verify target / health process).
6. Expect a closing receipt SMS.
7. Text follow-up: `send the error log`.

## Path 2 — decline and SMS

1. Decline or miss the call.
2. Finish the session by SMS (Brief, Fix, Execute, Verify over text).
