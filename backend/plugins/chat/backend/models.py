"""Backward-compatible chat model aliases.

Chat and coding now share the unified Session/SessionMessage tables in
``core.sessions.models``. Keep these aliases so existing chat plugin imports
continue to work while the rest of the codebase migrates.
"""

from core.sessions.models import Session as ChatSession
from core.sessions.models import SessionMessage as ChatMessage

__all__ = ["ChatSession", "ChatMessage"]
