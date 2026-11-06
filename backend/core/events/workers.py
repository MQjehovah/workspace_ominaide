"""Subscribe to events and process them (indexing, entity extraction)."""
from core.events.bus import subscribe
from core.ai.indexer import index_content
from core.config.settings import settings


def _is_internal(event) -> bool:
    """Events handled explicitly (bot runs, mail, RSS) skip generic worker LLM calls."""
    return (event.event_type or "").startswith(
        ("bot.run.", "mail.received", "dingtalk.", "article.", "rss.")
    )


# Internal CRUD namespaces produce API routes and code identifiers, not user
# knowledge, so they are never sent to the entity extractor.
_INTERNAL_ENTITY_SOURCES = {"bots", "mcp", "automation", "plugins", "rss", "article"}


def _skip_entities(event) -> bool:
    if _is_internal(event):
        return True
    return (event.event_type or "").split(".")[0] in _INTERNAL_ENTITY_SOURCES


async def indexing_handler(event):
    if not settings.data_layer_enabled or _is_internal(event):
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
    if not settings.memory_layer_enabled or _skip_entities(event):
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
