"""Persistent labels for desktop machines.

The WebSocket hub only knows online connections. This table keeps the display
name and last-seen time so renamed/offline machines remain visible in the app.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from core.database.session import async_session
from core.wschannel.models import Machine


async def register(
    user_id: int,
    machine_id: str,
    default_name: str,
    *,
    platform: str = "desktop",
) -> str:
    """Upsert a machine on connect and return its display name."""
    machine_id = machine_id.strip()
    default_name = (default_name or machine_id).strip()[:120]
    now = datetime.now()
    async with async_session() as db:
        row = (await db.execute(
            select(Machine).where(
                Machine.user_id == user_id,
                Machine.machine_id == machine_id,
            )
        )).scalar_one_or_none()
        if row is None:
            row = Machine(
                user_id=user_id,
                machine_id=machine_id,
                name=None,
                default_name=default_name,
                platform=platform,
                first_seen=now,
                last_seen=now,
            )
            db.add(row)
        else:
            row.default_name = default_name or row.default_name
            row.platform = platform or row.platform
            row.last_seen = now
        await db.commit()
        await db.refresh(row)
        return row.display_name()


async def touch(user_id: int, machine_id: str) -> None:
    try:
        async with async_session() as db:
            row = (await db.execute(
                select(Machine).where(
                    Machine.user_id == user_id,
                    Machine.machine_id == machine_id,
                )
            )).scalar_one_or_none()
            if row is not None:
                row.last_seen = datetime.now()
                await db.commit()
    except Exception:
        pass


async def list_machines(user_id: int) -> list[Machine]:
    async with async_session() as db:
        rows = await db.execute(
            select(Machine)
            .where(Machine.user_id == user_id)
            .order_by(Machine.last_seen.desc())
        )
        return list(rows.scalars().all())


async def rename(user_id: int, machine_id: str, name: str | None) -> Machine | None:
    async with async_session() as db:
        row = (await db.execute(
            select(Machine).where(
                Machine.user_id == user_id,
                Machine.machine_id == machine_id,
            )
        )).scalar_one_or_none()
        if row is None:
            return None
        row.name = (name or "").strip()[:120] or None
        await db.commit()
        await db.refresh(row)
        return row


async def remove(user_id: int, machine_id: str) -> bool:
    """Forget a machine (rename history, last seen). Only offline machines."""
    async with async_session() as db:
        row = (await db.execute(
            select(Machine).where(
                Machine.user_id == user_id,
                Machine.machine_id == machine_id,
            )
        )).scalar_one_or_none()
        if row is None:
            return False
        await db.delete(row)
        await db.commit()
        return True
