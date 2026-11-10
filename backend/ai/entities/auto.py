"""Manual graph extraction helpers for the Memory screen."""

from __future__ import annotations

from ai.entities.settings import mark_run
from core.database.session import async_session


async def extract_entities_for_user(user_id: int, limit: int = 8) -> dict:
    """Extract entities from recent notes, memories and mail."""
    from ai.entities.relations import _recent_texts
    from ai.retrieval.indexer import extract_and_store_entities

    async with async_session() as db:
        texts = await _recent_texts(db, user_id, limit=max(1, min(limit, 20)))
    count = 0
    for source_type, source_id, text in texts:
        title = next(
            (line.strip() for line in text.splitlines() if line.strip()),
            source_type,
        )[:120]
        await extract_and_store_entities(
            user_id=user_id,
            content=text,
            source_type=source_type,
            source_id=source_id,
            title=title,
        )
        count += 1
    await mark_run(user_id, "last_extract_at")
    return {"sources": count}
