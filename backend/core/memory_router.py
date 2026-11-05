"""User memory: profile, AI-learned preferences and the entity graph."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
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


class CandidateApprove(BaseModel):
    pass


class RecordUpdate(BaseModel):
    content: str | None = None
    importance: int | None = None


@router.get("/candidates")
async def candidates(
    status: str = Query("pending"),
    limit: int = Query(100, ge=1, le=300),
    user: dict = Depends(get_current_user),
):
    from core.memory_service import list_candidates

    rows = await list_candidates(user["id"], status, limit)
    return {"items": [_candidate_out(r) for r in rows]}


@router.post("/candidates/{candidate_id}/approve")
async def approve_candidate(candidate_id: int, user: dict = Depends(get_current_user)):
    from core.memory_service import approve_candidate as approve

    record = await approve(user["id"], candidate_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Candidate not found or already reviewed")
    return {"message": "Approved", "record_id": record.id}


@router.post("/candidates/{candidate_id}/reject")
async def reject_candidate(candidate_id: int, user: dict = Depends(get_current_user)):
    from core.memory_service import reject_candidate as reject

    ok = await reject(user["id"], candidate_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Candidate not found or already reviewed")
    return {"message": "Rejected"}


@router.get("/records")
async def records(
    q: str = Query(""),
    limit: int = Query(100, ge=1, le=300),
    user: dict = Depends(get_current_user),
):
    from core.memory_service import list_records

    rows = await list_records(user["id"], q, limit)
    return {"items": [_record_out(r) for r in rows]}


@router.patch("/records/{record_id}")
async def update_record(
    record_id: int,
    req: RecordUpdate,
    user: dict = Depends(get_current_user),
):
    from core.memory_service import update_record as update

    try:
        row = await update(user["id"], record_id, req.content, req.importance)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if row is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return _record_out(row)


@router.get("/graph")
async def graph(user: dict = Depends(get_current_user)):
    from core.memory_service import memory_graph

    return await memory_graph(user["id"])


@router.delete("/records/{record_id}")
async def forget_record(record_id: int, user: dict = Depends(get_current_user)):
    from core.memory_service import forget_record as forget

    ok = await forget(user["id"], record_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"message": "Forgotten"}


@router.post("/consolidate")
async def consolidate_memories(user: dict = Depends(get_current_user)):
    from core.memory_service import consolidate

    return await consolidate(user["id"])


def _candidate_out(row) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "content": row.content,
        "confidence": row.confidence,
        "source_type": row.source_type,
        "source_id": row.source_id,
        "source_ref": row.source_ref,
        "trust": row.trust,
        "status": row.status,
        "created_at": row.created_at,
    }


def _record_out(row) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "content": row.content,
        "confidence": row.confidence,
        "importance": row.importance,
        "source_type": row.source_type,
        "sources": row.sources,
        "status": row.status,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


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
