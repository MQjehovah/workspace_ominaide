from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.session import get_db
from core.auth.dependencies import get_current_user
from plugins.rss.backend.schemas import FeedCreate, FeedResponse, EntryResponse
from plugins.rss.backend import service
from plugins.rss.backend.models import Feed, Entry

router = APIRouter(prefix="/api/rss", tags=["rss"])


@router.get("/feeds", response_model=list[FeedResponse])
async def list_feeds(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await service.list_feeds(db, user["id"])


@router.post("/feeds", response_model=FeedResponse, status_code=201)
async def add_feed(req: FeedCreate, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await service.create_feed(db, user["id"], req.url)


@router.delete("/feeds/{feed_id}")
async def remove_feed(feed_id: int, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not await service.delete_feed(db, user["id"], feed_id):
        raise HTTPException(404)
    return {"message": "Deleted"}


@router.post("/feeds/{feed_id}/fetch")
async def fetch_feed(feed_id: int, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Feed).where(Feed.id == feed_id, Feed.user_id == user["id"]))
    feed = r.scalar_one_or_none()
    if not feed:
        raise HTTPException(404, detail="Feed not found")
    count = await service.fetch_feed_content(db, feed)
    return {"new_entries": count}


@router.get("/entries")
async def list_entries(
    feed_id: int | None = Query(None),
    unread: bool = False,
    starred: bool = False,
    page: int = 1,
    page_size: int = 20,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await service.list_entries(db, user["id"], feed_id, unread, starred, page, page_size)
    return {"items": [EntryResponse.model_validate(e) for e in items], "total": total}


@router.put("/entries/{entry_id}/read")
async def read_entry(entry_id: int, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    ok = await service.mark_read(db, user["id"], entry_id)
    if not ok:
        raise HTTPException(404)
    return {"message": "Read"}


@router.put("/entries/{entry_id}/star")
async def star_entry(entry_id: int, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    starred = await service.mark_starred(db, user["id"], entry_id)
    if starred is False:
        raise HTTPException(404)
    return {"starred": starred}


@router.get("/search")
async def search(
    q: str,
    feed_id: int | None = Query(None),
    page: int = 1,
    page_size: int = 20,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cond = [
        Feed.user_id == user["id"],
        or_(Entry.title.ilike(f"%{q}%"), Entry.summary.ilike(f"%{q}%"), Entry.content.ilike(f"%{q}%")),
    ]
    if feed_id:
        cond.append(Entry.feed_id == feed_id)
    base = select(Entry).join(Feed).where(*cond)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
    r = await db.execute(base.order_by(Entry.published.desc()).offset((page - 1) * page_size).limit(page_size))
    items = r.scalars().all()
    return {"items": [EntryResponse.model_validate(e) for e in items], "total": total}
