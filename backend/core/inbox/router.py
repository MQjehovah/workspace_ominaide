"""Deterministic unified-inbox API. No LLM and no skill: the inbox is a
product surface that groups items from mail, sources, DingTalk, todo and
schedule."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from core.auth.dependencies import get_current_user

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


@router.get("/groups")
async def groups(
    days: int = Query(3, ge=1, le=14),
    user: dict = Depends(get_current_user),
):
    from core.cos.service import triage

    return await triage(user["id"], days)


@router.get("/suggestions")
async def suggestions(
    refresh: bool = Query(False),
    user: dict = Depends(get_current_user),
):
    from core.workbench.suggestions import workbench_suggestions

    return await workbench_suggestions(user["id"], refresh=refresh)
