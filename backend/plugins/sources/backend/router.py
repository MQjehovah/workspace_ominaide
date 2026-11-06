from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.session import get_db
from core.auth.dependencies import get_current_user
from core.events.recorder import record_event
from plugins.sources.backend.schemas import (
    ItemResponse,
    ProviderResponse,
    SourceCreate,
    SourceResponse,
)
from plugins.sources.backend import service
from plugins.sources.backend.models import ContentItem, ContentSource
from plugins.sources.backend.providers import ProviderError, list_providers

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("/providers", response_model=list[ProviderResponse])
async def providers():
    return list_providers()


@router.get("", response_model=list[SourceResponse])
async def list_sources(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await service.list_sources(db, user["id"])


@router.post("", response_model=SourceResponse, status_code=201)
async def add_source(
    req: SourceCreate,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        source = await service.create_source(
            db,
            user["id"],
            req.provider,
            url=req.url,
            config=req.config,
        )
    except ProviderError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await record_event(
        db,
        user["id"],
        "sources.subscribed",
        "sources",
        source.id,
        f"添加资讯源: {source.title or source.url}",
        {
            "source_id": source.id,
            "provider": source.provider,
            "title": source.title,
            "url": source.url,
        },
    )
    return source


@router.delete("/{source_id}")
async def remove_source(
    source_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    source = (await db.execute(
        select(ContentSource).where(
            ContentSource.id == source_id,
            ContentSource.user_id == user["id"],
        )
    )).scalar_one_or_none()
    title = source.title or source.url if source else "未知"
    provider = source.provider if source else ""
    if not await service.delete_source(db, user["id"], source_id):
        raise HTTPException(404)
    await record_event(
        db,
        user["id"],
        "sources.unsubscribed",
        "sources",
        source_id,
        f"删除资讯源: {title}",
        {"source_id": source_id, "provider": provider, "title": title},
    )
    return {"message": "Deleted"}


@router.post("/{source_id}/fetch")
async def fetch_source(
    source_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    source = (await db.execute(
        select(ContentSource).where(
            ContentSource.id == source_id,
            ContentSource.user_id == user["id"],
        )
    )).scalar_one_or_none()
    if source is None:
        raise HTTPException(404, detail="Source not found")
    try:
        count = await service.fetch_source_content(db, source)
    except ProviderError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"抓取失败: {e}")
    return {"new_items": count}


@router.get("/items")
async def list_items(
    source_id: int | None = Query(None),
    unread: bool = False,
    starred: bool = False,
    page: int = 1,
    page_size: int = 20,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await service.list_items(
        db, user["id"], source_id, unread, starred, page, page_size
    )
    return {"items": await _with_source_titles(db, items), "total": total}


@router.get("/items/{item_id}")
async def get_item(
    item_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = (await db.execute(
        select(ContentItem)
        .join(ContentSource)
        .where(ContentItem.id == item_id, ContentSource.user_id == user["id"])
    )).scalar_one_or_none()
    if item is None:
        raise HTTPException(404, detail="Item not found")
    return (await _with_source_titles(db, [item]))[0]


@router.put("/items/{item_id}/read")
async def read_item(
    item_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await service.mark_read(db, user["id"], item_id):
        raise HTTPException(404)
    return {"message": "Read"}


@router.put("/items/{item_id}/star")
async def star_item(
    item_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    starred = await service.mark_starred(db, user["id"], item_id)
    if starred is False:
        raise HTTPException(404)
    return {"starred": starred}


@router.get("/digest")
async def sources_digest(
    hours: int = Query(24, ge=1, le=168),
    user=Depends(get_current_user),
):
    from plugins.sources.backend.digest import generate_sources_digest

    digest = await generate_sources_digest(user["id"], hours=hours, notify=False)
    return digest or {"count": 0, "items": [], "summary": ""}


@router.get("/search")
async def search(
    q: str,
    source_id: int | None = Query(None),
    page: int = 1,
    page_size: int = 20,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await service.search_items(
        db, user["id"], q, source_id, page, page_size
    )
    return {"items": await _with_source_titles(db, items), "total": total}


async def _with_source_titles(db: AsyncSession, items: list[ContentItem]) -> list[ItemResponse]:
    if not items:
        return []
    source_ids = {item.source_id for item in items}
    titles: dict[int, str] = {}
    try:
        rows = (await db.execute(
            select(ContentSource.id, ContentSource.title).where(
                ContentSource.id.in_(source_ids)
            )
        )).all()
        for source_id, title in rows:
            titles[source_id] = title or ""
    except Exception:
        pass
    out = []
    for item in items:
        payload = ItemResponse.model_validate(item)
        payload.source_title = titles.get(item.source_id)
        out.append(payload)
    return out
