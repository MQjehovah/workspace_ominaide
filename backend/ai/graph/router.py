from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from core.auth.dependencies import get_current_user
from ai.graph import service

router = APIRouter(prefix="/api/graph", tags=["graph"])
context_router = APIRouter(prefix="/api/context", tags=["context"])


class LinkCreate(BaseModel):
    from_type: str
    from_id: int
    to_type: str
    to_id: int
    relation: str = "related"
    confidence: float = 1.0
    source: str | None = None
    meta: dict | None = None


@router.post("/links")
async def create_link(req: LinkCreate, user: dict = Depends(get_current_user)):
    return await service.create_link(user["id"], **req.model_dump())


@router.get("/related")
async def related(
    type: str = Query(...),
    id: int = Query(...),
    user: dict = Depends(get_current_user),
):
    return {"items": await service.related(user["id"], type, id)}


@context_router.get("/build")
async def build_context(
    q: str = Query(""),
    type: str | None = Query(None),
    id: int | None = Query(None),
    limit: int = Query(6, ge=1, le=20),
    user: dict = Depends(get_current_user),
):
    return await service.build_context(
        user["id"], q, object_type=type, object_id=id, limit=limit
    )
