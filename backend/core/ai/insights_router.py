from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.auth.dependencies import get_current_user


router = APIRouter(prefix="/api/insights", tags=["insights"])


class DailyInsightResponse(BaseModel):
    id: int
    day: date
    summary: str
    highlights: list[str] | None = None
    patterns: list[str] | None = None
    suggestions: list[dict] | None = None
    stats: dict | None = None
    session_ids: list[str] | None = None
    generated_at: datetime | None = None

    model_config = {"from_attributes": True}


class RunInsightRequest(BaseModel):
    day: date | None = None
    force: bool = True


class RunWeeklyRequest(BaseModel):
    weeks: int = 1
    force: bool = True
    notify: bool = False


@router.get("/daily", response_model=list[DailyInsightResponse])
async def list_daily_insights(
    days: int = Query(7, ge=1, le=90),
    user: dict = Depends(get_current_user),
):
    from core.ai.daily_insights import get_recent_insights

    return await get_recent_insights(user["id"], days)


@router.get("/latest", response_model=DailyInsightResponse)
async def latest_daily_insight(user: dict = Depends(get_current_user)):
    from core.ai.daily_insights import get_recent_insights

    rows = await get_recent_insights(user["id"], 1)
    if not rows:
        raise HTTPException(status_code=404, detail="No daily insight yet")
    return rows[0]


@router.get("/daily/{day}", response_model=DailyInsightResponse)
async def get_daily_insight(day: date, user: dict = Depends(get_current_user)):
    from core.ai.insight_models import DailyInsight
    from core.database.session import async_session
    from sqlalchemy import select

    async with async_session() as db:
        row = (await db.execute(
            select(DailyInsight).where(
                DailyInsight.user_id == user["id"],
                DailyInsight.day == day,
            )
        )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Daily insight not found")
    return row


@router.post("/daily/run", response_model=DailyInsightResponse)
async def run_daily_insight(
    req: RunInsightRequest | None = None,
    user: dict = Depends(get_current_user),
):
    from core.ai.daily_insights import generate_daily_insight

    req = req or RunInsightRequest()
    day = req.day or date.today()
    row = await generate_daily_insight(user["id"], day, force=req.force, notify=False)
    if row is None:
        raise HTTPException(status_code=404, detail="No data for that day")
    return row


@router.post("/daily/backfill", response_model=list[DailyInsightResponse])
async def backfill_daily_insights(
    days: int = Query(7, ge=1, le=30),
    user: dict = Depends(get_current_user),
):
    """Generate missing reviews for the recent days (no notifications)."""
    from core.ai.daily_insights import ensure_daily_insight

    out = []
    today = date.today()
    for offset in range(days, 0, -1):
        row = await ensure_daily_insight(user["id"], today - timedelta(days=offset))
        if row is not None:
            out.append(row)
    return out


def _weekly_out(row) -> dict:
    return {
        "id": row.id,
        "week_start": row.week_start.isoformat(),
        "week_end": row.week_end.isoformat(),
        "period": {
            "start": row.week_start.isoformat(),
            "end": row.week_end.isoformat(),
        },
        "summary": row.summary,
        "wins": row.wins or [],
        "in_progress": row.in_progress or [],
        "risks": row.risks or [],
        "next_week": row.next_week or [],
        "stats": row.stats or {},
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
    }


@router.get("/weekly")
async def list_weekly_reviews(
    limit: int = Query(8, ge=1, le=52),
    user: dict = Depends(get_current_user),
):
    from core.ai.weekly_reviews import get_recent_weekly_reviews

    rows = await get_recent_weekly_reviews(user["id"], limit)
    return [_weekly_out(row) for row in rows]


@router.get("/weekly/latest")
async def latest_weekly_review(user: dict = Depends(get_current_user)):
    from core.ai.weekly_reviews import get_latest_weekly_review

    row = await get_latest_weekly_review(user["id"])
    if row is None:
        raise HTTPException(status_code=404, detail="No weekly review yet")
    return _weekly_out(row)


@router.post("/weekly/run")
async def run_weekly_review(
    req: RunWeeklyRequest | None = None,
    user: dict = Depends(get_current_user),
):
    from core.ai.weekly_reviews import generate_weekly_review
    from core.bots import registry

    req = req or RunWeeklyRequest()
    bot = await registry.get_active_bot(user["id"])
    row = await generate_weekly_review(
        user["id"],
        weeks=max(1, min(req.weeks, 4)),
        bot=bot,
        force=req.force,
        notify=req.notify,
    )
    return _weekly_out(row)
