"""oncall check | serve | voice sync"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import httpx

from oncall.config import Settings
from oncall.env_loader import load_dotenv
from oncall.voice_sync import sync_agent

_E164 = re.compile(r"^\+[1-9]\d{6,14}$")


def _status(label: str, ok: bool, detail: str = "") -> None:
    mark = "ok" if ok else "missing"
    line = f"  [{mark}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)


def _e164(number: str) -> bool:
    return bool(number and _E164.match(number.strip()))


def _https_public(url: str) -> bool:
    u = url.strip().rstrip("/")
    return u.startswith("https://") and "localhost" not in u and "127.0.0.1" not in u


def run_check(*, live: bool) -> int:
    load_dotenv()
    settings = Settings.from_env()
    failed = False

    if sys.version_info < (3, 11):
        print("Python 3.11+ required.", file=sys.stderr)
        return 1

    print("Server")
    _status("PUBLIC_BASE_URL", bool(settings.public_base_url), settings.public_base_url or "")
    if settings.public_base_url and not _https_public(settings.public_base_url):
        print("  [warn] Use https and a URL Twilio can reach (not localhost).")
        failed = True

    print("Database")
    db = Path(settings.database_path)
    try:
        db.parent.mkdir(parents=True, exist_ok=True)
        db.touch(exist_ok=True)
        _status("DATABASE_PATH writable", True, str(db))
    except OSError as exc:
        _status("DATABASE_PATH writable", False, str(exc))
        failed = True

    print("Runtime")
    _status("REPO_URL", bool(settings.repo_url), settings.repo_url or "")

    print("Phone")
    for name, val in (
        ("TWILIO_ACCOUNT_SID", settings.twilio_account_sid),
        ("TWILIO_AUTH_TOKEN", settings.twilio_auth_token),
        ("TWILIO_FROM_NUMBER", settings.twilio_from_number),
        ("MAINTAINER_NUMBER", settings.maintainer_number),
    ):
        _status(name, bool(val))
        if not val:
            failed = True
    if settings.twilio_from_number and not _e164(settings.twilio_from_number):
        print("  [warn] TWILIO_FROM_NUMBER should be E.164 (+15551234567).")
        failed = True
    if settings.maintainer_number and not _e164(settings.maintainer_number):
        print("  [warn] MAINTAINER_NUMBER should be E.164.")
        failed = True

    print("Voice")
    _status("ELEVENLABS_API_KEY", bool(settings.elevenlabs_api_key))
    _status("ELEVENLABS_AGENT_ID", bool(settings.elevenlabs_agent_id))
    if not settings.elevenlabs_api_key:
        failed = True

    print("Agent")
    mode = (settings.agent or "cursor").strip().lower()
    _status("AGENT", mode in {"cursor", "webhook"}, mode)
    if mode == "cursor":
        _status("CURSOR_API_KEY", bool(settings.cursor_api_key))
        if not settings.cursor_api_key or not settings.repo_url:
            failed = True
    elif mode == "webhook":
        _status("AGENT_WEBHOOK_URL", bool(settings.agent_webhook_url))
        if not settings.agent_webhook_url or not settings.repo_url:
            failed = True
    else:
        print("  [warn] AGENT must be cursor or webhook.")
        failed = True

    print("Alerts")
    if settings.alert_token:
        _status("ALERT_TOKEN", True, "POST /alerts requires Bearer token")
    else:
        print("  [warn] ALERT_TOKEN unset — anyone who can reach /alerts can open a call.")

    if not live:
        return 1 if failed else 0

    print("\nLive probes (no call placed)")
    sid, token = settings.twilio_account_sid, settings.twilio_auth_token
    if sid and token:
        r = httpx.get(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}.json",
            auth=(sid, token),
            timeout=30,
        )
        print(f"  twilio account: {r.status_code}")
        if r.status_code == 200:
            trial = r.json().get("type") == "Trial"
            if trial:
                print("  Twilio trial: dial only numbers verified in the console.")
        if r.status_code != 200:
            failed = True

    if mode == "cursor" and settings.cursor_api_key:
        r = httpx.get(
            "https://api.cursor.com/v1/me",
            headers={"Authorization": f"Bearer {settings.cursor_api_key}"},
            timeout=30,
        )
        print(f"  cursor: {r.status_code}")
        if r.status_code != 200:
            failed = True

    if settings.elevenlabs_api_key and settings.elevenlabs_agent_id:
        r = httpx.get(
            f"https://api.elevenlabs.io/v1/convai/agents/{settings.elevenlabs_agent_id}",
            headers={"xi-api-key": settings.elevenlabs_api_key},
            timeout=30,
        )
        print(f"  elevenlabs agent: {r.status_code}")
        if r.status_code == 200:
            pub = settings.public_base_url.rstrip("/")
            cfg = r.json().get("conversation_config") or {}
            prompt = (cfg.get("agent") or {}).get("prompt") or {}
            tools = prompt.get("tools") or []
            urls = [
                str(t.get("api_schema", {}).get("url", ""))
                for t in tools
                if isinstance(t, dict)
            ]
            if pub and not any(pub in u for u in urls):
                print(
                    "  [warn] Agent tool URLs may not match PUBLIC_BASE_URL — run: oncall voice sync"
                )
        elif r.status_code != 200:
            failed = True

    if mode == "webhook" and settings.agent_webhook_url:
        try:
            r = httpx.post(
                settings.agent_webhook_url,
                json={
                    "repo_url": settings.repo_url or "https://example.com/repo",
                    "instructions": "ping",
                    "verify_target": "https://example.com/health",
                },
                timeout=15,
            )
            print(f"  agent webhook: {r.status_code}")
        except httpx.HTTPError as exc:
            print(f"  agent webhook: error {type(exc).__name__}")
            failed = True

    pub = settings.public_base_url.rstrip("/")
    if pub:
        try:
            r = httpx.get(f"{pub}/docs", timeout=15, follow_redirects=True)
            print(f"  public URL /docs: {r.status_code}")
            if r.status_code != 200:
                print("  Run oncall serve and point PUBLIC_BASE_URL at this process.")
        except httpx.HTTPError as exc:
            print(f"  public URL: error {type(exc).__name__}")
            failed = True

    return 1 if failed else 0


def run_serve() -> int:
    load_dotenv()
    import uvicorn

    uvicorn.run(
        "oncall.app:build_default_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
    return 0


def run_voice_sync() -> int:
    load_dotenv()
    settings = Settings.from_env()
    try:
        agent_id, phase_url = sync_agent(
            api_key=settings.elevenlabs_api_key,
            agent_id=settings.elevenlabs_agent_id,
            public_base_url=settings.public_base_url,
        )
        print(agent_id)
        print(phase_url)
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="oncall")
    sub = parser.add_subparsers(dest="cmd", required=True)

    check_p = sub.add_parser("check", help="Validate .env")
    check_p.add_argument(
        "--live",
        action="store_true",
        help="Call vendor APIs (does not place a phone call)",
    )

    sub.add_parser("serve", help="Run the API on 127.0.0.1:8000")
    voice = sub.add_parser("voice", help="ElevenLabs voice")
    voice_sub = voice.add_subparsers(dest="voice_cmd", required=True)
    voice_sub.add_parser("sync", help="Sync agent tools to PUBLIC_BASE_URL")

    args = parser.parse_args(argv)
    if args.cmd == "check":
        raise SystemExit(run_check(live=args.live))
    if args.cmd == "serve":
        raise SystemExit(run_serve())
    if args.cmd == "voice" and args.voice_cmd == "sync":
        raise SystemExit(run_voice_sync())
    parser.print_help()
    raise SystemExit(2)


if __name__ == "__main__":
    main()
