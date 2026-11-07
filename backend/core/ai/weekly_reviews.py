"""Weekly review pipeline.

A weekly review is generated from the stored daily reviews plus the week's
todos/schedule/mail, then persisted in ``weekly_reviews`` so it can be opened
again at any time. The hourly daily brief is intentionally not persisted; this
is the long-term review record.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from core.logging import get_logger

log = get_logger(__name__)


def _week_bounds(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    return today - timedelta(days=6), today


async def generate_weekly_review(
    user_id: int,
    *,
    weeks: int = 1,
    bot=None,
    force: bool = False,
    notify: bool = False,
):
    """Generate or reuse one user's review for the current week."""
    from sqlalchemy import select

    from core.ai.insight_models import WeeklyReview
    from core.cos.service import weekly_review
    from core.database.session import async_session
    from core.skills.loader import get_skill

    week_start, week_end = _week_bounds()

    async with async_session() as db:
        existing = (await db.execute(
            select(WeeklyReview).where(
                WeeklyReview.user_id == user_id,
                WeeklyReview.week_start == week_start,
            )
        )).scalar_one_or_none()
        if existing is not None and not force:
            return existing

    skill = get_skill("weekly-review")
    data = await weekly_review(
        user_id,
        weeks=weeks,
        bot=bot,
        extra_system=skill.body if skill else None,
    )

    async with async_session() as db:
        row = (await db.execute(
            select(WeeklyReview).where(
                WeeklyReview.user_id == user_id,
                WeeklyReview.week_start == week_start,
            )
        )).scalar_one_or_none()
        if row is None:
            row = WeeklyReview(user_id=user_id, week_start=week_start, week_end=week_end)
            db.add(row)
        row.week_end = week_end
        row.summary = str(data.get("summary") or "")
        row.wins = data.get("wins") or []
        row.in_progress = data.get("in_progress") or []
        row.risks = data.get("risks") or []
        row.next_week = data.get("next_week") or []
        row.stats = data.get("stats") or {}
        row.generated_at = datetime.utcnow()
        await db.flush()
        await db.refresh(row)
        if notify:
            await _notify_weekly_review(db, user_id, row)
        await db.commit()
        await db.refresh(row)
        return row


async def _notify_weekly_review(db, user_id: int, row) -> None:
    try:
        from plugins.notifications.backend.router import notify_user
        from plugins.notifications.backend.service import create_notification

        n = await create_notification(
            db,
            user_id,
            "📅 本周回顾",
            (row.summary or "")[:500],
            "weekly_review",
            "/insights",
            actions=[{"key": "open", "label": "查看回顾", "kind": "open", "link": "/insights"}],
            dedupe_key=f"weekly_review:{row.week_start.isoformat()}",
        )
        await db.flush()
        await notify_user(user_id, {
            "type": "new_notification",
            "id": n.id,
            "title": "📅 本周回顾",
            "body": (row.summary or "")[:500],
            "link": "/insights",
        })
    except Exception as e:
        log.warning(f"[weekly] notify error: {e}")


async def get_recent_weekly_reviews(user_id: int, limit: int = 8) -> list:
    from sqlalchemy import select

    from core.ai.insight_models import WeeklyReview
    from core.database.session import async_session

    async with async_session() as db:
        rows = await db.execute(
            select(WeeklyReview)
            .where(WeeklyReview.user_id == user_id)
            .order_by(WeeklyReview.week_start.desc())
            .limit(max(1, limit))
        )
        return list(rows.scalars().all())


async def get_latest_weekly_review(user_id: int):
    rows = await get_recent_weekly_reviews(user_id, 1)
    return rows[0] if rows else None
