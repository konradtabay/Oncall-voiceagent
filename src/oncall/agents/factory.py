"""Build the configured coding-agent backend."""

from __future__ import annotations

from oncall.agents.cursor_impl import CursorImplementer, cursor_from_settings
from oncall.agents.webhook_impl import WebhookImplementer
from oncall.config import Settings


def build_implementer(settings: Settings) -> CursorImplementer | WebhookImplementer:
    mode = (settings.agent or "cursor").strip().lower()
    if mode == "webhook":
        if not settings.agent_webhook_url:
            raise ValueError("AGENT=webhook requires AGENT_WEBHOOK_URL")
        return WebhookImplementer(settings.agent_webhook_url)
    if mode != "cursor":
        raise ValueError(f"Unknown AGENT={settings.agent!r}; use cursor or webhook")
    if not settings.cursor_api_key:
        raise ValueError("AGENT=cursor requires CURSOR_API_KEY")
    return cursor_from_settings(settings.cursor_api_key)
