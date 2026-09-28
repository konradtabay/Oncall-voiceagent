# Setup

Run this on a machine your monitor can reach. Twilio and ElevenLabs must reach `PUBLIC_BASE_URL` over HTTPS.

## 1. Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Requires Python 3.11+.

## 2. Server

```bash
oncall serve
```

Runs on `127.0.0.1:8000`. Use one process (SQLite).

Expose it with ngrok or your host:

```bash
ngrok http 8000
```

Set `PUBLIC_BASE_URL` to the tunnel’s **https** URL. When that URL changes, run:

```bash
oncall voice sync
```

A stale URL gives a connected call that stays silent.

## 3. Database

`DATABASE_PATH` defaults to `oncall.sqlite3` in the working directory. Point it at any path the process can create and write.

## 4. Runtime

- `REPO_URL` — Git repo the coding agent may change (your service, not this repo).
- Each alert’s `verify_target` — URL the agent checks after the fix (must be reachable from the agent, not `localhost` on your laptop).

## 5. Twilio

Create a number. Put in `.env`:

- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER` (E.164, e.g. `+15551234567`)
- `MAINTAINER_NUMBER` — default callee when `to_number` is omitted on `/alerts`

Trial accounts only dial numbers verified in the Twilio console. Outbound voice webhooks are set by this app; you do not paste a voice URL in the console for outbound.

## 6. ElevenLabs

Create an agent in Eleven Agents or leave `ELEVENLABS_AGENT_ID` empty and run:

```bash
oncall voice sync
```

Copy the printed agent id into `.env` if it was created for you. The voice model on the call is **gemini-2.5-flash** (configured by sync). That is separate from your coding agent.

## 7. Coding agent

**Cursor (`AGENT=cursor`)**

- `CURSOR_API_KEY`
- Cloud Agents enabled; connect GitHub so `REPO_URL` is visible to Cursor.

**Webhook (`AGENT=webhook`)**

- `AGENT_WEBHOOK_URL` — see [agents.md](agents.md) and [examples/agent_webhook.py](../examples/agent_webhook.py).

## 8. Check

```bash
oncall check
oncall check --live
```

`--live` hits vendor APIs and does **not** place a call.

## 9. First alert

```bash
export PUBLIC_BASE_URL=https://your-tunnel.example
export MAINTAINER_NUMBER=+1...
curl -sS -X POST "$PUBLIC_BASE_URL/alerts" \
  -H 'Content-Type: application/json' \
  -d "{\"summary\":\"Worker down\",\"logs\":\"exit 1\",\"verify_target\":\"https://your-service/health\"}"
```

This spends Twilio and ElevenLabs quota.

Optional: set `ALERT_TOKEN` and send `Authorization: Bearer $ALERT_TOKEN`.

## 10. Monitor without a product yet

Cron a health check and POST on failure:

```bash
if ! curl -sf https://your-service/health; then
  curl -sS -X POST "$PUBLIC_BASE_URL/alerts" \
    -H "Authorization: Bearer $ALERT_TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{"summary":"health check failed","logs":"curl exit non-zero","verify_target":"https://your-service/health"}'
fi
```

## 11. Keep running (systemd example)

```ini
[Unit]
Description=oncall voice
After=network.target

[Service]
WorkingDirectory=/opt/oncall-voiceagent
EnvironmentFile=/opt/oncall-voiceagent/.env
ExecStart=/opt/oncall-voiceagent/.venv/bin/oncall serve
Restart=on-demand

[Install]
WantedBy=multi-user.target
```

Adjust paths. Run ngrok or your reverse proxy separately so `PUBLIC_BASE_URL` stays valid.
