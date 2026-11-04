"""Coding run creation and lookup.

The generic ``bot_runs`` row owns lifecycle/audit; ``coding_runs`` owns the
coding-specific project/branch/engine fields.
"""
from sqlalchemy import select

from core.database.session import async_session
from core.coding.models import CodingRun


async def create_coding_run(
    user_id: int,
    bot,
    project: str,
    instruction: str,
    *,
    branch: str | None = None,
    engine: str = "builtin",
    parent_run_id: int | None = None,
    session_id: str | None = None,
):
    from core.bots import runner
    from core.bots.context import get_current_session_id

    session_id = session_id or get_current_session_id()
    run = await runner.create_run(
        user_id,
        bot,
        instruction,
        trigger="coding",
        parent_run_id=parent_run_id,
        session_id=session_id,
        auto_start=False,
    )
    async with async_session() as db:
        db.add(
            CodingRun(
                run_id=run.id,
                user_id=user_id,
                project_path=project,
                branch=branch,
                engine=engine,
            )
        )
        await db.commit()

    runner.enqueue_run(run.id)
    return run


async def get_coding_run(run_id: int) -> CodingRun | None:
    async with async_session() as db:
        return (
            await db.execute(select(CodingRun).where(CodingRun.run_id == run_id))
        ).scalar_one_or_none()
