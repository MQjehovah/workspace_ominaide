"""Subscribe to events and process them (indexing, entities, memory candidates)."""
import json

from core.events.bus import subscribe
from core.ai.indexer import index_content
from core.config.settings import settings

# One unified memory-extraction path: external message events are analysed by
# the event worker, regardless of which plugin produced them.
MEMORY_EVENT_TYPES = {"mail.received", "dingtalk.message"}


def _is_internal(event) -> bool:
    """Events handled explicitly (bot runs, mail) skip generic worker LLM calls."""
    return (event.event_type or "").startswith(("bot.run.", "mail.received"))


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
    if not settings.memory_layer_enabled or _is_internal(event):
        return
    from core.ai.indexer import extract_and_store_entities
    await extract_and_store_entities(
        user_id=event.user_id,
        content=str(event.details or ""),
        source_type=event.entity_type or event.event_type,
        source_id=event.id,
        title=event.summary or "",
    )


async def memory_handler(event):
    """Extract review candidates from external message events in one place."""
    if not settings.memory_layer_enabled or not settings.memory_event_extract_enabled:
        return
    if event.event_type not in MEMORY_EVENT_TYPES:
        return

    details = event.details
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except Exception:
            details = {}
    if not isinstance(details, dict):
        details = {}

    parts = [
        event.summary or "",
        details.get("subject") or "",
        details.get("from") or "",
        details.get("content") or details.get("text") or "",
    ]
    text = "\n".join(str(part) for part in parts if part).strip()
    if len(text) < 20:
        return

    from core.memory_service import ingest_text

    try:
        await ingest_text(
            event.user_id,
            text[:12000],
            source_type=event.event_type.split(".")[0],
            source_id=event.entity_id,
            source_ref={"event_id": event.id},
            trust="untrusted",
        )
    except Exception as e:
        print(f"[events] memory extract failed: {e}")


def register_workers():
    subscribe(indexing_handler)
    subscribe(entity_handler)
    subscribe(memory_handler)
