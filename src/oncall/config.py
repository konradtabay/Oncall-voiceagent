"""Environment for the orchestrator. Missing keys leave ports unwired."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from_number: str
    elevenlabs_api_key: str
    elevenlabs_agent_id: str
    cursor_api_key: str
    cursor_repo_url: str
    public_base_url: str
    database_path: str
    maintainer_number: str
    twilio_machine_detection: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            twilio_account_sid=os.environ.get("TWILIO_ACCOUNT_SID", ""),
            twilio_auth_token=os.environ.get("TWILIO_AUTH_TOKEN", ""),
            twilio_from_number=os.environ.get("TWILIO_FROM_NUMBER", ""),
            elevenlabs_api_key=os.environ.get("ELEVENLABS_API_KEY", ""),
            elevenlabs_agent_id=os.environ.get("ELEVENLABS_AGENT_ID", ""),
            cursor_api_key=os.environ.get("CURSOR_API_KEY", ""),
            cursor_repo_url=os.environ.get("CURSOR_REPO_URL", ""),
            public_base_url=os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:8000"),
            database_path=os.environ.get("DATABASE_PATH", "oncall.sqlite3"),
            maintainer_number=os.environ.get("MAINTAINER_NUMBER", ""),
            twilio_machine_detection=os.environ.get("TWILIO_MACHINE_DETECTION", ""),
        )
