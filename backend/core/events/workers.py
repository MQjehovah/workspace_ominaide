"""Subscribe to events and process them (indexing, entity extraction)."""
import asyncio

from core.events.bus import subscribe
from ai.retrieval.indexer import index_content
from core.config.settings import settings


def _is_internal(event) -> bool:
    """Events handled explicitly (bot runs, mail, sources) skip generic worker LLM calls."""
    return (event.event_type or "").startswith(
        ("bot.run.", "mail.received", "dingtalk.", "sources.", "article.", "rss.")
    )


# Internal CRUD namespaces produce API routes and code identifiers, not user
# knowledge, so they are never sent to the entity extractor.
_INTERNAL_ENTITY_SOURCES = {
    "bots", "mcp", "automation", "plugins", "sources", "rss", "article",
}


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
    from ai.entities.settings import auto_extract_enabled, auto_relations_enabled
    from ai.retrieval.indexer import extract_and_store_entities

    if not await auto_extract_enabled(event.user_id):
        return
    text = str(event.details or "")
    source_type = event.entity_type or event.event_type
    source_id = event.entity_id or event.id
    title = event.summary or ""
    await extract_and_store_entities(
        user_id=event.user_id,
        content=text,
        source_type=source_type,
        source_id=source_id,
        title=title,
    )
    try:
        if await auto_relations_enabled(event.user_id):
            from ai.entities.relations import extract_relations_from_text

            asyncio.create_task(
                extract_relations_from_text(
                    event.user_id,
                    f"{title}\n{text}",
                    source_type,
                    int(source_id),
                )
            )
    except Exception:
        pass


def register_workers():
    subscribe(indexing_handler)
    subscribe(entity_handler)
