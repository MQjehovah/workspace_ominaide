"""Memory curator: decay, expiry and salience refresh."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from ai.memory.models import MemoryRecord
from core.database.session import async_session
from core.logging import get_logger

log = get_logger(__name__)


async def curate_user(user_id: int) -> dict:
    now = datetime.now()
    expired = 0
    updated = 0
    async with async_session() as db:
        rows = list((await db.execute(
            select(MemoryRecord).where(
                MemoryRecord.user_id == user_id,
                MemoryRecord.status == "active",
            )
        )).scalars().all())
        for row in rows:
            if row.expires_at is not None and row.expires_at < now:
                row.status = "deleted"
                row.valid_to = now
                expired += 1
                continue
            salience = int(
                (row.importance or 50) * 0.6
                + (row.confidence or 60) * 0.2
                + min(int(row.use_count or 0), 20) * 1.0
            )
            salience = max(0, min(salience, 100))
            if row.salience != salience:
                row.salience = salience
                updated += 1
        await db.commit()
    return {"user_id": user_id, "expired": expired, "updated": updated}


async def curate_all() -> dict:
    from core.auth.domain.models import User

    async with async_session() as db:
        user_ids = list((await db.execute(select(User.id))).scalars().all())
    total_expired = 0
    total_updated = 0
    for user_id in user_ids:
        result = await curate_user(int(user_id))
        total_expired += result["expired"]
        total_updated += result["updated"]
    return {"users": len(user_ids), "expired": total_expired, "updated": total_updated}
