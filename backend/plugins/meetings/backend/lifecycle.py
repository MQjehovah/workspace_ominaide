"""Meetings plugin startup hooks."""

from __future__ import annotations


async def startup() -> None:
    from plugins.meetings.backend.service import recover_pending_jobs

    await recover_pending_jobs()
