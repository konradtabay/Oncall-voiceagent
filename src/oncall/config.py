"""Environment for the orchestrator. Missing keys leave ports unwired."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _repo_url() -> str:
    return (
        os.environ.get("REPO_URL", "").strip()
        or os.environ.get("CURSOR_REPO_URL", "").strip()
    )


@dataclass(frozen=True)
class Settings:
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from_number: str
    elevenlabs_api_key: str
    elevenlabs_agent_id: str
    cursor_api_key: str
    repo_url: str
    public_base_url: str
    database_path: str
    maintainer_number: str
    twilio_machine_detection: str
    agent: str
    agent_webhook_url: str
    alert_token: str
    diagnose_timeout_secs: float

    @property
    def cursor_repo_url(self) -> str:
        """Legacy alias."""
        return self.repo_url

    @classmethod
    def from_env(cls) -> "Settings":
        timeout_raw = os.environ.get("DIAGNOSE_TIMEOUT_SECS", "90")
        try:
            diagnose_timeout = float(timeout_raw)
        except ValueError:
            diagnose_timeout = 90.0
        return cls(
            twilio_account_sid=os.environ.get("TWILIO_ACCOUNT_SID", ""),
            twilio_auth_token=os.environ.get("TWILIO_AUTH_TOKEN", ""),
            twilio_from_number=os.environ.get("TWILIO_FROM_NUMBER", ""),
            elevenlabs_api_key=os.environ.get("ELEVENLABS_API_KEY", ""),
            elevenlabs_agent_id=os.environ.get("ELEVENLABS_AGENT_ID", ""),
            cursor_api_key=os.environ.get("CURSOR_API_KEY", ""),
            repo_url=_repo_url(),
            public_base_url=os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:8000"),
            database_path=os.environ.get("DATABASE_PATH", "oncall.sqlite3"),
            maintainer_number=os.environ.get("MAINTAINER_NUMBER", ""),
            twilio_machine_detection=os.environ.get("TWILIO_MACHINE_DETECTION", ""),
            agent=os.environ.get("AGENT", "cursor"),
            agent_webhook_url=os.environ.get("AGENT_WEBHOOK_URL", "").strip(),
            alert_token=os.environ.get("ALERT_TOKEN", "").strip(),
            diagnose_timeout_secs=diagnose_timeout,
        )
