#!/usr/bin/env python3
"""Point the ElevenLabs agent at gemini-2.5-flash and the phase/updates webhooks."""

from __future__ import annotations

import sys

from oncall.env_loader import load_dotenv
from oncall.config import Settings
from oncall.voice_sync import sync_agent


def main() -> int:
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


if __name__ == "__main__":
    sys.exit(main())
