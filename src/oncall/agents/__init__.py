"""Coding-agent backends: Cursor cloud or a generic webhook."""

from oncall.agents.factory import build_implementer
from oncall.agents.protocol import Implementer

__all__ = ["Implementer", "build_implementer"]
