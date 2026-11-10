"""Automatic proposal mining jobs."""

from __future__ import annotations

from datetime import datetime

from ai.cognition.miner import mine_user
from core.jobs.service import enqueue, register_handler
from core.scheduler import PeriodicJob


async def enqueue_mine_user(user_id: int) -> None:
    bucket = datetime.now().strftime("%Y%m%d%H%M")
    await enqueue(
        "cognition.mine.user",
        {"user_id": int(user_id)},
        idempotency_key=f"cognition:mine:{int(user_id)}:{bucket}",
    )


async def mine_user_job(job) -> dict:
    user_id = int((job.payload or {}).get("user_id") or 0)
    if not user_id:
        return {"skipped": True, "reason": "missing user_id"}
    from core.observability.context import set_user_id

    set_user_id(user_id)
    try:
        return await mine_user(user_id)
    finally:
        set_user_id(None)


async def enqueue_all_users() -> dict:
    from core.auth.domain.models import User
    from core.database.session import async_session
    from sqlalchemy import select

    async with async_session() as db:
        user_ids = list((await db.execute(select(User.id))).scalars().all())
    for user_id in user_ids:
        await enqueue_mine_user(int(user_id))
    return {"users": len(user_ids)}


async def tick_active_goals() -> dict:
    """Recover goal dispatch after restarts and missed run-finished events."""
    from sqlalchemy import select

    from ai.cognition.models import Goal
    from ai.cognition.orchestrator import tick_goal
    from core.database.session import async_session
    from core.observability.context import set_user_id

    async with async_session() as db:
        rows = list(
            (
                await db.execute(
                    select(Goal).where(
                        Goal.status.in_(("planning", "ready", "running", "waiting", "verifying"))
                    ).limit(50)
                )
            )
            .scalars()
            .all()
        )
    count = 0
    for goal in rows:
        set_user_id(goal.user_id)
        try:
            await tick_goal(goal.user_id, goal.id)
            count += 1
        except Exception:
            continue
        finally:
            set_user_id(None)
    return {"goals": count}


async def backfill_entities() -> dict:
    from ai.entities.backfill import backfill_memory_edges
    from ai.entities.extract import seed_from_profile
    from core.auth.domain.models import User
    from core.database.session import async_session
    from sqlalchemy import select

    async with async_session() as db:
        user_ids = list((await db.execute(select(User.id))).scalars().all())
        for user_id in user_ids:
            await seed_from_profile(db, int(user_id))
        await db.commit()
    result = await backfill_memory_edges()
    return {"users": len(user_ids), **result}


register_handler("cognition.mine.user", mine_user_job)

JOBS = [
    PeriodicJob(
        key="cognition.mine",
        owner="cognition",
        handler=enqueue_all_users,
        interval_seconds=1800,
        timeout_seconds=300,
        run_on_start=False,
    ),
    PeriodicJob(
        key="cognition.goals.tick",
        owner="cognition",
        handler=tick_active_goals,
        interval_seconds=60,
        timeout_seconds=120,
        run_on_start=False,
    ),
    PeriodicJob(
        key="cognition.entities.backfill",
        owner="cognition",
        handler=backfill_entities,
        interval_seconds=86400,
        timeout_seconds=300,
        run_on_start=True,
    ),
]
