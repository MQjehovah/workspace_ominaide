"""One-time backfill of legacy ``memory_edges`` into entity mentions."""

from __future__ import annotations

from sqlalchemy import func, select

from ai.entities.extract import attach_memory_entities
from ai.entities.models import EntityMention
from ai.entities.service import resolve_entity
from ai.memory.models import MemoryEdge, MemoryRecord
from core.database.session import async_session


_TYPE_MAP = {"person": "person", "project": "project", "entity": "topic"}


async def backfill_memory_edges() -> dict:
    async with async_session() as db:
        edges = list((await db.execute(select(MemoryEdge))).scalars().all())
        created = 0
        for edge in edges:
            record = await db.get(MemoryRecord, edge.memory_id)
            if record is None or record.user_id != edge.user_id:
                continue
            entity_type = _TYPE_MAP.get(str(edge.target_type), "topic")
            entity = await resolve_entity(
                db,
                edge.user_id,
                entity_type,
                edge.target_name,
                source="memory_edge",
            )
            if entity is None:
                continue
            before = int((await db.execute(
                select(func.count()).select_from(EntityMention).where(
                    EntityMention.user_id == edge.user_id,
                    EntityMention.entity_id == entity.id,
                    EntityMention.source_type == "memory",
                    EntityMention.source_id == record.id,
                )
            )).scalar_one() or 0)
            if before == 0:
                await attach_memory_entities(db, edge.user_id, record)
                after = int((await db.execute(
                    select(func.count()).select_from(EntityMention).where(
                        EntityMention.user_id == edge.user_id,
                        EntityMention.entity_id == entity.id,
                        EntityMention.source_type == "memory",
                        EntityMention.source_id == record.id,
                    )
                )).scalar_one() or 0)
                created += max(0, after - before)
        await db.commit()
    return {"edges": len(edges), "mentions_created": created}
