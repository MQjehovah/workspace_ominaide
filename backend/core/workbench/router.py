from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select

from core.auth.dependencies import get_current_user
from core.ai.context import schedule_items, todo_items
from core.database.session import async_session

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


def _event_out(item: dict) -> dict:
    meta = item.get("meta") or {}
    return {
        "id": item.get("source_id"),
        "title": item.get("title") or "日程",
        "start_time": item.get("time"),
        "end_time": meta.get("end"),
        "notes": item.get("summary") or "",
        "source": item.get("source") or "manual",
    }


def _todo_out(item: dict) -> dict:
    meta = item.get("meta") or {}
    return {
        "id": item.get("source_id"),
        "title": item.get("title") or "待办",
        "description": item.get("summary") or "",
        "due_date": meta.get("due"),
        "status": "pending",
        "priority": meta.get("priority") or 0,
    }


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

    events, todos, files, notes, projects = (
        await asyncio.gather(
            safe(
                schedule_items(
                    user_id,
                    start=start,
                    end=end,
                    limit=20,
                )
            ),
            safe(todo_items(user_id, limit=100)),
            safe(_recent_files(user_id)),
            safe(_recent_notes(user_id)),
            safe(_recent_projects(user_id)),
        )
    )

    return {
        "events": [_event_out(item) for item in (events or [])],
        "todos": [_todo_out(item) for item in (todos or [])],
        "recent": {
            "files": files or [],
            "notes": notes or [],
            "projects": projects or [],
        },
        "generated_at": now.isoformat(timespec="seconds"),
    }
