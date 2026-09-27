# On-call

A watched process goes down. This calls the person who can approve a fix, tells them what broke and the one fix, and runs it when they say yes. They stay on the line. A text goes out when the fix starts. They hear when the process is back.

https://github.com/user-attachments/assets/cf582145-422d-4d0f-b7ee-9e362e37147e

[Full video](https://drive.google.com/drive/home)

## What it does

An alert opens one incident. It carries the logs and enough context to name the failure and one fix. The call does not start until that is ready, so the first thing they hear is the problem and the fix, in plain language.

They can ask questions and change the fix. There is still one fix. A different idea replaces it. There is no menu.

When they tell it to run the fix:

1. A text goes out. It names what broke and what is being done.
2. The fix runs while the call stays up.
3. It checks that the process is back, and says so on the call.
4. If the check passes, the call ends. A closing text lists every issue on that call, the fix, and that it worked.
5. If the check fails, the call stays up. Nothing retries until they approve a new fix.

A missed call does not go to voicemail. The same problem and the same fix arrive by text, and the rest of the loop is the same conversation.

A second alert waits. One incident at a time, in the order they arrived. A text after a receipt still reaches the same incident. It does not start another call, and it is not treated as approval to run a fix.

## Where companies use it

The person who can approve a fix is not sitting in front of the dashboard.

- A training or inference worker dies overnight. The on-call engineer gets one call: the runner is down, the queue is stuck, and the fix is to clear the bad key and restart it. They say yes from the phone. The call stays up until health is back.
- A payments or webhook worker stops taking events. One person gets the call, approves the restart, and gets a text that the fix started and another when traffic is moving again.
- A deploy breaks health checks. The call says what the release broke and the one rollback or restart. They approve it. The line stays open until the check passes.
- A queue stalls. Jobs pile up because a consumer is blocked. Same loop: what is stuck, the one repair, yes, then a check that the queue is draining.
- A small team with no overnight desk. One phone number. One open incident. The next alert waits instead of paging everyone.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn oncall.app:build_default_app --factory --host 0.0.0.0 --port 8000
```

Demo page: http://127.0.0.1:8000/demo

Fill `.env` from `.env.example`. `PUBLIC_BASE_URL` has to be the HTTPS address the phone provider can reach.
