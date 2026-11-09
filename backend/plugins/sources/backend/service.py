
from core.logging import get_logger
log = get_logger(__name__)
import asyncio
import feedparser
import httpx
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta

from ai.indexer import index_content
from plugins.sources.backend.models import ContentItem, ContentSource
from plugins.sources.backend.providers import ProviderError, get_provider


async def list_sources(db: AsyncSession, user_id: int):
    r = await db.execute(
        select(ContentSource)
        .where(ContentSource.user_id == user_id)
        .order_by(ContentSource.created_at.desc())
    )
    return list(r.scalars().all())


async def create_source(
    db: AsyncSession,
    user_id: int,
    provider_key: str,
    url: str | None = None,
    config: dict | None = None,
):
    provider = get_provider(provider_key)
    merged = dict(config or {})
    if url and url.strip():
        merged["url"] = url.strip()
    fetch_url, title = provider.build(merged)

    existing = (await db.execute(
        select(ContentSource).where(
            ContentSource.user_id == user_id,
            ContentSource.provider == provider_key,
            ContentSource.url == fetch_url,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return existing

    source = ContentSource(
        user_id=user_id,
        provider=provider_key,
        config=merged,
        url=fetch_url,
        title=title,
    )
    db.add(source)
    await db.flush()
    await db.refresh(source)
    return source


async def delete_source(db: AsyncSession, user_id: int, source_id: int) -> bool:
    source = (await db.execute(
        select(ContentSource).where(
            ContentSource.id == source_id,
            ContentSource.user_id == user_id,
        )
    )).scalar_one_or_none()
    if source is None:
        return False
    await db.delete(source)
    await db.flush()
    return True


async def list_items(
    db: AsyncSession,
    user_id: int,
    source_id: int | None = None,
    unread: bool = False,
    starred: bool = False,
    page: int = 1,
    page_size: int = 20,
):
    q = (
        select(ContentItem)
        .join(ContentSource, ContentItem.source_id == ContentSource.id)
        .where(ContentSource.user_id == user_id)
    )
    if source_id:
        q = q.where(ContentItem.source_id == source_id)
    if unread:
        q = q.where(ContentItem.read == False)  # noqa: E712
    if starred:
        q = q.where(ContentItem.starred == True)  # noqa: E712
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    q = q.order_by(ContentItem.published.desc()).offset((page - 1) * page_size).limit(page_size)
    r = await db.execute(q)
    return list(r.scalars().all()), total


async def search_items(
    db: AsyncSession,
    user_id: int,
    query: str,
    source_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
):
    cond = [
        ContentSource.user_id == user_id,
        or_(
            ContentItem.title.ilike(f"%{query}%"),
            ContentItem.summary.ilike(f"%{query}%"),
            ContentItem.content.ilike(f"%{query}%"),
        ),
    ]
    if source_id:
        cond.append(ContentItem.source_id == source_id)
    base = select(ContentItem).join(ContentSource).where(*cond)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
    r = await db.execute(
        base.order_by(ContentItem.published.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(r.scalars().all()), total


async def mark_read(db: AsyncSession, user_id: int, item_id: int):
    item = (await db.execute(
        select(ContentItem)
        .join(ContentSource)
        .where(ContentItem.id == item_id, ContentSource.user_id == user_id)
    )).scalar_one_or_none()
    if item is None:
        return False
    item.read = True
    await db.flush()
    return True


async def mark_starred(db: AsyncSession, user_id: int, item_id: int):
    item = (await db.execute(
        select(ContentItem)
        .join(ContentSource)
        .where(ContentItem.id == item_id, ContentSource.user_id == user_id)
    )).scalar_one_or_none()
    if item is None:
        return False
    item.starred = not item.starred
    await db.flush()
    return item.starred


async def fetch_source_content(db: AsyncSession, source: ContentSource) -> int:
    try:
        resp = await httpx.AsyncClient(timeout=20).get(source.url, follow_redirects=True)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        if source.provider == "rss" or not source.title:
            source.title = feed.feed.get("title", source.title)
        source.last_fetch = datetime.utcnow()
        new = 0
        new_items = []
        for entry in feed.entries:
            guid = entry.get("id") or entry.get("link") or ""
            if not guid:
                continue
            exists = await db.execute(
                select(ContentItem).where(
                    ContentItem.source_id == source.id,
                    ContentItem.guid == guid,
                )
            )
            if exists.scalar_one_or_none():
                continue
            published = None
            if entry.get("published_parsed"):
                published = datetime(*entry.published_parsed[:6])
            entry_content = entry.get("content")
            content_value = (
                entry_content[0].get("value")
                if entry_content
                else entry.get("summary")
            )
            item = ContentItem(
                source_id=source.id,
                guid=guid,
                title=entry.get("title", ""),
                link=entry.get("link"),
                summary=(entry.get("summary") or "")[:1000],
                content=content_value,
                author=entry.get("author"),
                published=published,
            )
            db.add(item)
            new_items.append(item)
            new += 1
        await db.flush()
        for item in new_items:
            try:
                from core.events.recorder import record_event

                await record_event(
                    db,
                    source.user_id,
                    "sources.item.new",
                    "sources",
                    item.id,
                    f"新内容: {item.title or ''}",
                    {
                        "source": source.title or source.url,
                        "provider": source.provider,
                        "url": item.link,
                        "title": item.title,
                        "summary": (item.summary or item.content or "")[:800],
                    },
                )
            except Exception:
                pass
            asyncio.create_task(index_content(
                user_id=source.user_id,
                source_type="source_item",
                source_id=item.id,
                title=item.title,
                content=item.summary or item.content or str(item.id),
                metadata={"link": item.link, "provider": source.provider} if item.link else {"provider": source.provider},
            ))
        try:
            from core.events.recorder import record_event

            await record_event(
                db,
                source.user_id,
                "sources.refreshed",
                "sources",
                source.id,
                f"资讯源刷新: {source.title or source.url}",
                {"source": source.title or source.url, "provider": source.provider, "new_items": new},
            )
        except Exception:
            pass
        return new
    except Exception as ex:
        log.warning(f"[sources] fetch error {source.url}: {ex}")
        raise


async def refresh_due_sources(interval_seconds: int) -> dict:
    """Refresh sources whose last fetch is older than the interval."""
    from core.database.session import async_session

    cutoff = datetime.utcnow() - timedelta(seconds=max(60, int(interval_seconds)))
    async with async_session() as db:
        ids = list((await db.execute(
            select(ContentSource.id).where(
                or_(
                    ContentSource.last_fetch == None,  # noqa: E711
                    ContentSource.last_fetch < cutoff,
                )
            )
        )).scalars().all())

    total = 0
    for source_id in ids:
        async with async_session() as db:
            source = await db.get(ContentSource, source_id)
            if source is None:
                continue
            try:
                total += await fetch_source_content(db, source)
                await db.commit()
            except Exception as exc:
                await db.rollback()
                log.warning("[sources] refresh %s failed: %s", source_id, exc)
    return {"sources": len(ids), "new": total}
