from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select

from core.auth.dependencies import get_current_user
from core.cos import collectors
from core.database.session import async_session
from core.workbench.suggestions import workbench_suggestions
from core.workbench.dingtalk_actions import dingtalk_actions

router = APIRouter(prefix="/api/workbench", tags=["workbench"])


async def _recent_files(user_id: int) -> list[dict]:
    from plugins.files.backend.models import File

    async with async_session() as db:
        rows = (
            await db.execute(
                select(File)
                .where(
                    File.user_id == user_id,
                    File.status == "active",
                    File.is_folder == False,  # noqa: E712
                )
                .order_by(File.created_at.desc())
                .limit(5)
            )
        ).scalars().all()
    return [
        {
            "id": row.id,
            "original_name": row.original_name,
            "mime_type": row.mime_type,
            "size": row.size,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


async def _recent_notes(user_id: int) -> list[dict]:
    from plugins.notes.backend.models import PluginNote

    async with async_session() as db:
        rows = (
            await db.execute(
                select(PluginNote)
                .where(
                    PluginNote.user_id == user_id,
                    PluginNote.is_folder == 0,
                )
                .order_by(PluginNote.updated_at.desc())
                .limit(5)
            )
        ).scalars().all()
    return [
        {
            "id": row.id,
            "title": row.title,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]


async def _recent_projects(user_id: int) -> list[dict]:
    from plugins.projects.backend.models import Project

    async with async_session() as db:
        rows = (
            await db.execute(
                select(Project)
                .where(Project.user_id == user_id)
                .order_by(Project.updated_at.desc())
                .limit(5)
            )
        ).scalars().all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]


@router.get("/summary")
async def workbench_summary(user: dict = Depends(get_current_user)):
    user_id = user["id"]
    now = datetime.now()
    start = datetime(now.year, now.month, now.day)
    end = start + timedelta(days=1)

    async def safe(coro):
        try:
            return await coro
        except Exception:
            return None

    from core.cos.service import triage

    triage_data, events, todos, files, notes, projects, suggestions = (
        await asyncio.gather(
            safe(triage(user_id, 3)),
            safe(
                collectors.schedule_items(
                    user_id,
                    start=start,
                    end=end,
                    limit=20,
                )
            ),
            safe(collectors.todo_items(user_id, limit=100)),
            safe(_recent_files(user_id)),
            safe(_recent_notes(user_id)),
            safe(_recent_projects(user_id)),
            safe(workbench_suggestions(user_id)),
        )
    )

    triage_data = triage_data or {}
    groups = triage_data.get("groups") or {}
    pending = (
        len(groups.get("urgent") or [])
        + len(groups.get("needs_reply") or [])
        + len(groups.get("today") or [])
    )
    all_items = [
        item
        for values in groups.values()
        if isinstance(values, list)
        for item in values
    ]
    mail_unread = sum(
        1
        for item in all_items
        if item.get("source") == "mail" and not (item.get("meta") or {}).get("read")
    )
    dingtalk_count = sum(
        1 for item in all_items if item.get("source") == "dingtalk"
    )

    return {
        "triage": triage_data,
        "inbox": {
            "pending": pending,
            "urgent": len(groups.get("urgent") or []),
            "mail": mail_unread,
            "dingtalk": dingtalk_count,
        },
        "events": events or [],
        "todos": todos or [],
        "recent": {
            "files": files or [],
            "notes": notes or [],
            "projects": projects or [],
        },
        "suggestions": (suggestions or {}).get("suggestions") or [],
        "generated_at": now.isoformat(timespec="seconds"),
    }


@router.get("/dingtalk-actions")
async def get_dingtalk_actions(
    refresh: bool = False,
    user: dict = Depends(get_current_user),
):
    return await dingtalk_actions(user["id"], refresh=refresh)
