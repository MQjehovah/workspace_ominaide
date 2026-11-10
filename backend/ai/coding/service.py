"""Coding run creation and lookup backed by the unified Session model."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from core.config.settings import settings
from core.database.session import async_session
from core.sessions import service as session_service
from ai.bots.models import Run


@dataclass
class CodingContext:
    run_id: int
    user_id: int
    project_path: str
    branch: str | None
    engine: str
    session_id: str | None


async def create_coding_run(
    user_id: int,
    bot,
    project: str,
    instruction: str,
    *,
    branch: str | None = None,
    engine: str | None = None,
    parent_run_id: int | None = None,
    session_id: str | None = None,
    goal_id: int | None = None,
    task_id: int | None = None,
):
    from ai.bots import runner
    from ai.bots.context import get_current_session_id

    engine = (engine or settings.coding_engine or "builtin").lower()
    session_id = session_id or get_current_session_id() or session_service.new_session_id()
    metadata = {
        "project_path": project,
        "engine": engine,
        "branch": branch,
    }
    await session_service.ensure_session(
        user_id,
        session_id,
        bot_id=bot.id if bot is not None else None,
        title=instruction[:60],
        objective=instruction,
        metadata=metadata,
    )
    run = await runner.create_run(
        user_id,
        bot,
        instruction,
        trigger="coding",
        agent=engine,
        meta=metadata,
        goal_id=goal_id,
        task_id=task_id,
        parent_run_id=parent_run_id,
        session_id=session_id,
        auto_start=False,
    )
    await session_service.add_message(
        user_id,
        session_id,
        "user",
        instruction,
        bot_id=bot.id if bot is not None else None,
        run_id=run.id,
        kind="text",
    )
    await session_service.set_active_run(user_id, session_id, run.id, "active")
    runner.enqueue_run(run.id)
    return run


async def get_coding_run(run_id: int) -> CodingContext | None:
    async with async_session() as db:
        run = (
            await db.execute(
                select(Run).where(Run.id == run_id, Run.trigger == "coding")
            )
        ).scalar_one_or_none()
        if run is None:
            return None
        meta = run.meta or {}
        return CodingContext(
            run_id=run.id,
            user_id=run.user_id,
            project_path=str(meta.get("project_path") or ""),
            branch=meta.get("branch"),
            engine=str(run.agent or meta.get("engine") or "builtin"),
            session_id=run.session_id,
        )
