"""Cross-device index of coding sessions reported by desktop machines."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.session import async_session
from core.wschannel.models import CodingSession


def _pick(item: dict, *keys, default=""):
    for key in keys:
        value = item.get(key)
        if value is not None:
            return value
    return default


async def replace_snapshot(
    user_id: int, machine_id: str, sessions: list[dict]
) -> None:
    now = datetime.now()
    seen: set[str] = set()
    async with async_session() as db:
        rows = list(
            (
                await db.execute(
                    select(CodingSession).where(
                        CodingSession.user_id == user_id,
                        CodingSession.machine_id == machine_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        by_id = {row.session_id: row for row in rows}
        for item in sessions or []:
            if not isinstance(item, dict):
                continue
            session_id = str(_pick(item, "id", "session_id")).strip()
            if not session_id:
                continue
            seen.add(session_id)
            row = by_id.get(session_id)
            if row is None:
                row = CodingSession(
                    user_id=user_id,
                    machine_id=machine_id,
                    session_id=session_id,
                )
                db.add(row)
            row.agent = str(_pick(item, "agent", default="opencode"))[:32]
            row.title = str(item.get("title") or "")[:500]
            row.project = str(
                _pick(item, "project", "directory") or ""
            )[:1000]
            row.native = bool(item.get("native"))
            row.running = bool(item.get("running"))
            row.updated_ms = int(item.get("updated") or 0)
            row.last_seen = now
        for row in rows:
            if row.session_id not in seen:
                await db.delete(row)
        await db.commit()


async def list_sessions(user_id: int) -> list[CodingSession]:
    async with async_session() as db:
        rows = await db.execute(
            select(CodingSession)
            .where(CodingSession.user_id == user_id)
            .order_by(
                CodingSession.updated_ms.desc(), CodingSession.last_seen.desc()
            )
        )
        return list(rows.scalars().all())


async def get_session(
    user_id: int, machine_id: str, session_id: str
) -> CodingSession | None:
    async with async_session() as db:
        return (
            await db.execute(
                select(CodingSession).where(
                    CodingSession.user_id == user_id,
                    CodingSession.machine_id == machine_id,
                    CodingSession.session_id == session_id,
                )
            )
        ).scalar_one_or_none()


async def set_running(
    user_id: int, machine_id: str, session_id: str, running: bool
) -> None:
    async with async_session() as db:
        row = (
            await db.execute(
                select(CodingSession).where(
                    CodingSession.user_id == user_id,
                    CodingSession.machine_id == machine_id,
                    CodingSession.session_id == session_id,
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            row.running = running
            row.last_seen = datetime.now()
            await db.commit()


async def remove_machine(user_id: int, machine_id: str) -> None:
    async with async_session() as db:
        await db.execute(
            delete(CodingSession).where(
                CodingSession.user_id == user_id,
                CodingSession.machine_id == machine_id,
            )
        )
        await db.commit()


async def remove_session(user_id: int, machine_id: str, session_id: str) -> None:
    async with async_session() as db:
        await db.execute(
            delete(CodingSession).where(
                CodingSession.user_id == user_id,
                CodingSession.machine_id == machine_id,
                CodingSession.session_id == session_id,
            )
        )
        await db.commit()
