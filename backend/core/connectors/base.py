from __future__ import annotations

from typing import Protocol


class Connector(Protocol):
    """Minimal connector contract for incremental data sources."""

    key: str
    title: str

    async def authenticate(self) -> bool: ...

    async def sync(self, *, cursor: str | None = None) -> dict:
        """Return {"cursor": str|None, "items": int, "error": str|None}."""
        ...

    async def health(self) -> dict: ...
