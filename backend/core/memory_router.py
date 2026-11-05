"""User memory: profile, AI-learned preferences and the entity graph."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from core.auth.dependencies import get_current_user
from core.database.session import async_session, engine


router = APIRouter(prefix="/api/memory", tags=["memory"])


def _loads(value):
    if not value:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return None


@router.get("/profile")
async def memory_profile(user: dict = Depends(get_current_user)):
    from sqlalchemy import select
    from core.auth.domain.models import UserProfile

    async with async_session() as db:
        profile = (await db.execute(
            select(UserProfile).where(UserProfile.user_id == user["id"])
        )).scalar_one_or_none()
    if profile is None:
        return {
            "user_id": user["id"], "name": None, "role": None, "company": None,
            "contacts": [], "projects": [], "preferences": {},
        }
    prefs = _loads(profile.preferences) or {}
    return {
        "user_id": profile.user_id,
        "name": profile.name,
        "role": profile.role,
        "company": profile.company,
        "contacts": _loads(profile.contacts) or [],
        "projects": _loads(profile.projects) or [],
        "preferences": prefs,
        "interests": prefs.get("interests") or [],
        "habits": prefs.get("habits") or [],
        "insights": prefs.get("insights") or {},
        "last_analysis": prefs.get("last_analysis"),
    }


@router.get("/entities")
async def list_entities(
    entity_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    """List extracted people/projects/terms. Returns [] outside PostgreSQL."""
    if engine.dialect.name != "postgresql":
        return {"items": [], "counts": {}, "supported": False}
    try:
        async with engine.begin() as conn:
            rows = (await conn.execute(
                text(
                    "SELECT doc_key, title, metadata, created_at FROM embeddings "
                    "WHERE collection = 'entities' AND user_id = :uid "
                    "ORDER BY created_at DESC LIMIT :limit"
                ),
                {"uid": user["id"], "limit": limit},
            )).mappings().all()
    except Exception as e:
        print(f"[memory] entities error: {e}")
        return {"items": [], "counts": {}, "supported": False}

    items = []
    counts: dict[str, int] = {}
    for row in rows:
        meta = row["metadata"]
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        meta = meta or {}
        etype = meta.get("type") or "term"
        if entity_type and etype != entity_type:
            continue
        counts[etype] = counts.get(etype, 0) + 1
        items.append({
            "id": row["doc_key"],
            "name": row["title"],
            "type": etype,
            "sources": meta.get("sources") or [],
            "first_seen": meta.get("first_seen"),
            "last_seen": meta.get("last_seen"),
        })
    return {"items": items, "counts": counts, "supported": True}


@router.delete("/entities/{doc_key}")
async def delete_entity(doc_key: str, user: dict = Depends(get_current_user)):
    """Forget one entity; the underlying source content is untouched."""
    if engine.dialect.name != "postgresql":
        raise HTTPException(status_code=404, detail="Entity not found")
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                "DELETE FROM embeddings WHERE collection = 'entities' "
                "AND user_id = :uid AND doc_key = :key"
            ),
            {"uid": user["id"], "key": doc_key},
        )
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {"message": "Entity forgotten"}
