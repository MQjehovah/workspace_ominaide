
from core.logging import get_logger
log = get_logger(__name__)
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from core.auth.dependencies import get_current_user
from core.config.settings import settings

router = APIRouter(prefix="/api", tags=["search"])


class SearchRequest(BaseModel):
    q: str
    types: list[str] | None = None
    top_k: int = 10


class SearchResult(BaseModel):
    type: str
    title: str
    snippet: str
    score: float
    source_id: int | None = None
    link: str | None = None


class SearchResponse(BaseModel):
    results: list[SearchResult]


async def _keyword_search(user_id: int, q: str, types: list[str] | None, limit: int) -> list[SearchResult]:
    """Database LIKE fallback so search still works without embeddings."""
    from sqlalchemy import or_, select
    from core.database.session import async_session

    like = f"%{q}%"
    wanted = set(types or [])
    out: list[SearchResult] = []

    async with async_session() as db:
        if not wanted or "file" in wanted:
            from plugins.files.backend.models import File

            rows = list((await db.execute(
                select(File).where(
                    File.user_id == user_id,
                    File.status == "active",
                    File.is_folder == False,
                    File.original_name.ilike(like),
                ).limit(limit)
            )).scalars().all())
            out.extend(SearchResult(
                type="file", title=f.original_name,
                snippet=f"{f.folder_path or '/'} · {f.size or 0} bytes",
                score=0.5, source_id=f.id, link="/files",
            ) for f in rows)

        if not wanted or "note" in wanted:
            from plugins.notes.backend.models import PluginNote

            rows = list((await db.execute(
                select(PluginNote).where(
                    PluginNote.user_id == user_id,
                    PluginNote.is_folder == 0,
                    or_(PluginNote.title.ilike(like), PluginNote.content.ilike(like)),
                ).limit(limit)
            )).scalars().all())
            out.extend(SearchResult(
                type="note", title=n.title or "无标题",
                snippet=(n.content or "")[:200],
                score=0.5, source_id=n.id, link=f"/notes?id={n.id}",
            ) for n in rows)

        if not wanted or "source_item" in wanted:
            from plugins.sources.backend.models import ContentItem, ContentSource

            rows = list((await db.execute(
                select(ContentItem).join(
                    ContentSource, ContentItem.source_id == ContentSource.id
                ).where(
                    ContentSource.user_id == user_id,
                    or_(
                        ContentItem.title.ilike(like),
                        ContentItem.summary.ilike(like),
                        ContentItem.content.ilike(like),
                    ),
                ).limit(limit)
            )).scalars().all())
            out.extend(SearchResult(
                type="source_item", title=item.title or "",
                snippet=(item.summary or "")[:200],
                score=0.45, source_id=item.id, link="/sources",
            ) for item in rows)

        if not wanted or "event" in wanted:
            from plugins.schedule.backend.models import Event

            rows = list((await db.execute(
                select(Event).where(
                    Event.user_id == user_id,
                    or_(Event.title.ilike(like), Event.notes.ilike(like)),
                ).limit(limit)
            )).scalars().all())
            out.extend(SearchResult(
                type="event", title=e.title,
                snippet=(e.notes or e.start_time.strftime("%Y-%m-%d %H:%M"))[:200],
                score=0.45, source_id=e.id, link="/schedule",
            ) for e in rows)

        if not wanted or "email" in wanted:
            try:
                from plugins.mail.backend.models import MailMessage

                rows = list((await db.execute(
                    select(MailMessage).where(
                        MailMessage.user_id == user_id,
                        or_(
                            MailMessage.subject.ilike(like),
                            MailMessage.preview.ilike(like),
                            MailMessage.content.ilike(like),
                        ),
                    ).limit(limit)
                )).scalars().all())
                out.extend(SearchResult(
                    type="email", title=m.subject or "(无主题)",
                    snippet=(m.ai_summary or m.preview or "")[:200],
                    score=0.45, source_id=m.id, link="/mail",
                ) for m in rows)
            except Exception:
                pass

    return out


@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest, user: dict = Depends(get_current_user)):
    q = (req.q or "").strip()
    if not q:
        return SearchResponse(results=[])

    results: list[SearchResult] = []
    seen: set[tuple] = set()

    # Keyword results are always available, even when embeddings are offline.
    try:
        for item in await _keyword_search(user["id"], q, req.types, req.top_k):
            key = (item.type, item.source_id)
            if key in seen:
                continue
            seen.add(key)
            results.append(item)
    except Exception as e:
        log.warning(f"[search] keyword error: {e}")

    # Semantic results enrich the keyword pass when the vector store is available.
    if settings.data_layer_enabled:
        try:
            from core.ai.embeddings import generate_embedding
            from core.ai import vector_store

            vector = await generate_embedding(q)
            if vector is not None:
                hits = await vector_store.search(
                    "omnidocs",
                    user["id"],
                    vector,
                    limit=req.top_k,
                    source_types=req.types,
                )
                for h in hits:
                    key = (h.get("source_type") or "unknown", h.get("source_id"))
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(SearchResult(
                        type=h.get("source_type") or "unknown",
                        title=h.get("title") or "",
                        snippet=(h.get("content") or "")[:200],
                        score=h.get("score", 0.0),
                        source_id=h.get("source_id"),
                        link=f"/{h.get('source_type', '')}/{h.get('source_id', '')}",
                    ))
        except Exception as e:
            log.warning(f"[search] semantic error: {e}")

    results.sort(key=lambda x: x.score, reverse=True)
    return SearchResponse(results=results[:req.top_k])
