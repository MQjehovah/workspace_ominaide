import feedparser
import httpx
from sqlalchemy import select, delete, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from plugins.rss.backend.models import Feed, Entry


async def list_feeds(db: AsyncSession, user_id: int):
    r = await db.execute(select(Feed).where(Feed.user_id == user_id).order_by(Feed.created_at.desc()))
    return list(r.scalars().all())


async def create_feed(db: AsyncSession, user_id: int, url: str):
    feed = Feed(user_id=user_id, url=url)
    db.add(feed)
    await db.flush()
    await db.refresh(feed)
    return feed


async def delete_feed(db: AsyncSession, user_id: int, feed_id: int):
    f = await db.execute(select(Feed).where(Feed.id == feed_id, Feed.user_id == user_id))
    f = f.scalar_one_or_none()
    if not f:
        return False
    await db.delete(f)
    await db.flush()
    return True


async def list_entries(
    db: AsyncSession,
    user_id: int,
    feed_id: int | None = None,
    unread: bool = False,
    starred: bool = False,
    page: int = 1,
    page_size: int = 20,
):
    q = select(Entry).join(Feed, Entry.feed_id == Feed.id).where(Feed.user_id == user_id)
    if feed_id:
        q = q.where(Entry.feed_id == feed_id)
    if unread:
        q = q.where(Entry.read == False)
    if starred:
        q = q.where(Entry.starred == True)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    q = q.order_by(Entry.published.desc().nullslast()).offset((page - 1) * page_size).limit(page_size)
    r = await db.execute(q)
    return list(r.scalars().all()), total


async def mark_read(db: AsyncSession, user_id: int, entry_id: int):
    e = await db.execute(select(Entry).join(Feed).where(Entry.id == entry_id, Feed.user_id == user_id))
    e = e.scalar_one_or_none()
    if not e:
        return False
    e.read = True
    await db.flush()
    return True


async def mark_starred(db: AsyncSession, user_id: int, entry_id: int):
    e = await db.execute(select(Entry).join(Feed).where(Entry.id == entry_id, Feed.user_id == user_id))
    e = e.scalar_one_or_none()
    if not e:
        return False
    e.starred = not e.starred
    await db.flush()
    return e.starred


async def fetch_feed_content(db: AsyncSession, feed: Feed) -> int:
    try:
        resp = await httpx.AsyncClient(timeout=15).get(feed.url, follow_redirects=True)
        f = feedparser.parse(resp.text)
        feed.title = f.feed.get("title", feed.title)
        feed.last_fetch = datetime.utcnow()
        new = 0
        for e in f.entries:
            guid = e.get("id") or e.get("link") or ""
            if not guid:
                continue
            existing = await db.execute(select(Entry).where(Entry.feed_id == feed.id, Entry.guid == guid))
            if existing.scalar_one_or_none():
                continue
            published = None
            if e.get("published_parsed"):
                published = datetime(*e.published_parsed[:6])
            entry = Entry(
                feed_id=feed.id,
                guid=guid,
                title=e.get("title", ""),
                link=e.get("link"),
                summary=(e.get("summary") or "")[:500],
                content=e.get("content", [{}])[0].get("value") if e.get("content") else e.get("summary"),
                author=e.get("author"),
                published=published,
            )
            db.add(entry)
            new += 1
        await db.flush()
        return new
    except Exception as ex:
        print(f"[rss] fetch error {feed.url}: {ex}")
        return 0
