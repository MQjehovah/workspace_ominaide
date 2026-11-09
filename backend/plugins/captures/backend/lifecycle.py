"""Captures plugin startup hooks."""

from __future__ import annotations


async def startup() -> None:
    from plugins.captures.backend.service import register_capture_handlers

    register_capture_handlers()
