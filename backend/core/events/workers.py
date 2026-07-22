"""Subscribe to events and process them (indexing, entity extraction, etc.)."""
from core.events.bus import subscribe
from core.ai.indexer import index_content
from core.config.settings import settings


async def indexing_handler(event):
    if not settings.data_layer_enabled:
        return
    await index_content(
        user_id=event.user_id,
        source_type="activity",
        source_id=event.id,
        title=event.summary or event.event_type,
        content=str(event.details or ""),
        metadata={"link": f"/activities/{event.id}", "event_type": event.event_type},
    )


async def entity_handler(event):
    if not settings.memory_layer_enabled:
        return
    from core.ai.indexer import extract_and_store_entities
    await extract_and_store_entities(
        user_id=event.user_id,
        content=str(event.details or ""),
        source_type=event.entity_type or event.event_type,
        source_id=event.id,
        title=event.summary or "",
    )


def register_workers():
    subscribe(indexing_handler)
    subscribe(entity_handler)
