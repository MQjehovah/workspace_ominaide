"""API for business-object references and comments."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.auth.dependencies import get_current_user
from app.objects.registry import OBJECT_TYPES, resolve_object, search_objects
from app.objects.service import (
    ObjectCommentError,
    comment_out,
    create_comment,
    delete_comment,
    list_comments,
    update_comment,
)

router = APIRouter(prefix="/api/objects", tags=["objects"])


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    kind: str = "comment"
    title: str | None = None
    parent_id: int | None = None
    metadata: dict | None = None


class CommentUpdate(BaseModel):
    content: str | None = Field(default=None, max_length=20000)
    title: str | None = None


@router.get("/types")
async def object_types(user: dict = Depends(get_current_user)):
    return {"types": [{"key": key, "label": label} for key, label in OBJECT_TYPES.items()]}


@router.get("/search")
async def search(
    q: str = Query(""),
    types: str = Query(""),
    limit: int = Query(20, ge=1, le=50),
    user: dict = Depends(get_current_user),
):
    items = await search_objects(user["id"], q, types or None, limit)
    return {"items": items}


@router.get("/{object_type}/{object_id}")
async def get_object(
    object_type: str,
    object_id: int,
    user: dict = Depends(get_current_user),
):
    item = await resolve_object(user["id"], object_type, object_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Object not found")
    return item


@router.get("/{object_type}/{object_id}/comments")
async def get_comments(
    object_type: str,
    object_id: int,
    include_deleted: bool = Query(False),
    user: dict = Depends(get_current_user),
):
    item = await resolve_object(user["id"], object_type, object_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Object not found")
    rows = await list_comments(
        user["id"], object_type, object_id, include_deleted=include_deleted
    )
    return {"object": item, "items": [comment_out(row) for row in rows]}


@router.post("/{object_type}/{object_id}/comments", status_code=201)
async def add_comment(
    object_type: str,
    object_id: int,
    req: CommentCreate,
    user: dict = Depends(get_current_user),
):
    try:
        return await create_comment(
            user["id"], object_type, object_id,
            content=req.content,
            kind=req.kind,
            title=req.title,
            author="user",
            parent_id=req.parent_id,
            metadata=req.metadata,
        )
    except ObjectCommentError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/comments/{comment_id}")
async def edit_comment(
    comment_id: int,
    req: CommentUpdate,
    user: dict = Depends(get_current_user),
):
    if req.content is None and req.title is None:
        raise HTTPException(status_code=400, detail="content or title is required")
    try:
        row = await update_comment(
            user["id"], comment_id, content=req.content, title=req.title
        )
    except ObjectCommentError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if row is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    return row


@router.delete("/comments/{comment_id}")
async def remove_comment(
    comment_id: int,
    user: dict = Depends(get_current_user),
):
    ok = await delete_comment(user["id"], comment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Comment not found")
    return {"message": "Deleted"}
