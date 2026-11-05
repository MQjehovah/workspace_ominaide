"""Chief-of-Staff scenario API."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.auth.dependencies import get_current_user


router = APIRouter(prefix="/api/cos", tags=["cos"])


class MeetingPrepRequest(BaseModel):
    title: str = ""
    start: str | None = None
    attendees: list[str] = Field(default_factory=list)
    query: str | None = None


class DraftReplyRequest(BaseModel):
    source: str = "mail"
    message_id: int | None = None
    message: str | None = None
    subject: str | None = None
    tone: str = "professional"
    instructions: str | None = None


@router.get("/triage")
async def cos_triage(
    days: int = Query(3, ge=1, le=14),
    user: dict = Depends(get_current_user),
):
    from core.cos.service import triage

    return await triage(user["id"], days)


@router.get("/daily-brief")
async def cos_daily_brief(
    day: date | None = Query(None),
    user: dict = Depends(get_current_user),
):
    from core.cos.service import daily_brief

    return await daily_brief(user["id"], day)


@router.post("/meeting-prep")
async def cos_meeting_prep(
    req: MeetingPrepRequest,
    user: dict = Depends(get_current_user),
):
    from core.cos.service import meeting_prep

    return await meeting_prep(
        user["id"],
        title=req.title,
        start=req.start,
        attendees=req.attendees,
        query=req.query,
    )


@router.get("/weekly-review")
async def cos_weekly_review(
    weeks: int = Query(1, ge=1, le=4),
    user: dict = Depends(get_current_user),
):
    from core.cos.service import weekly_review

    return await weekly_review(user["id"], weeks)


@router.post("/draft-reply")
async def cos_draft_reply(
    req: DraftReplyRequest,
    user: dict = Depends(get_current_user),
):
    from core.cos.service import draft_reply

    draft = await draft_reply(
        user["id"],
        source=req.source,
        message_id=req.message_id,
        message=req.message,
        subject=req.subject,
        tone=req.tone,
        instructions=req.instructions,
    )
    if draft is None:
        raise HTTPException(status_code=404, detail="Message not found or empty")
    return draft
