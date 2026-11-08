from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from core.auth.dependencies import get_current_user
from core.database.session import async_session
from core.graph.models import SyncState

router = APIRouter(prefix="/api/connectors", tags=["connectors"])

_CONNECTORS = [
    {"key": "mail", "title": "邮件"},
    {"key": "schedule", "title": "日程"},
    {"key": "files", "title": "文件"},
    {"key": "notes", "title": "笔记"},
    {"key": "meetings", "title": "会议纪要"},
]


class SyncStateUpdate(BaseModel):
    cursor: str | None = None
    status: str = "idle"
    error: str | None = None


def _out(row: SyncState | None, connector: dict) -> dict:
    return {
        "connector": connector["key"],
        "title": connector["title"],
        "cursor": row.cursor if row else None,
        "status": row.status if row else "idle",
        "error": row.error if row else None,
        "last_sync_at": row.last_sync_at.isoformat()
        if row and row.last_sync_at
        else None,
    }


@router.get("")
async def list_connectors(user: dict = Depends(get_current_user)):
    async with async_session() as db:
        rows = (
            await db.execute(
                select(SyncState).where(SyncState.user_id == user["id"])
            )
        ).scalars().all()
    by_key = {row.connector: row for row in rows}
    return {"items": [_out(by_key.get(item["key"]), item) for item in _CONNECTORS]}


@router.put("/{connector}")
async def update_sync_state(
    connector: str,
    req: SyncStateUpdate,
    user: dict = Depends(get_current_user),
):
    if connector not in {item["key"] for item in _CONNECTORS}:
        raise HTTPException(404, detail="Connector not found")
    async with async_session() as db:
        row = (
            await db.execute(
                select(SyncState).where(
                    SyncState.user_id == user["id"],
                    SyncState.connector == connector,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = SyncState(user_id=user["id"], connector=connector)
            db.add(row)
        row.cursor = req.cursor
        row.status = req.status
        row.error = req.error
        if req.status in {"idle", "ok", "done"}:
            row.last_sync_at = datetime.now()
        await db.commit()
        await db.refresh(row)
    spec = next(item for item in _CONNECTORS if item["key"] == connector)
    return _out(row, spec)
