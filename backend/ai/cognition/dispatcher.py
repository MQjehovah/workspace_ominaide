"""Dispatcher: map ready Tasks to Runs."""

from __future__ import annotations

from sqlalchemy import func, select

from ai.bots import runner
from ai.bots.models import Run
from ai.bots.registry import get_active_bot
from ai.cognition import goals as goal_service
from core.database.session import async_session


async def _active_run(task_id: int) -> bool:
    async with async_session() as db:
        count = (await db.execute(
            select(func.count()).select_from(Run).where(
                Run.task_id == task_id,
                Run.status.in_(("queued", "running", "waiting_approval")),
            )
        )).scalar_one()
    return int(count or 0) > 0


async def _attempts(task_id: int) -> int:
    async with async_session() as db:
        count = (await db.execute(
            select(func.count()).select_from(Run).where(Run.task_id == task_id)
        )).scalar_one()
    return int(count or 0)


def _task_prompt(goal: dict, task: dict) -> str:
    lines = [
        f"目标：{goal.get('title')}",
        f"背景：{goal.get('description') or ''}",
        f"当前 Task：{task.get('title')}",
        f"说明：{task.get('description') or ''}",
    ]
    acceptance = task.get("acceptance")
    if acceptance:
        lines.append(f"验收标准：{acceptance}")
    lines.append("只完成这个 Task，不要越界执行其他 Task。完成后汇报结果和依据。")
    return "\n".join(lines)


async def dispatch_goal(user_id: int, goal_id: int, *, limit: int = 2) -> dict | None:
    goal = await goal_service.get_goal(user_id, goal_id)
    if goal is None:
        return None
    if goal["status"] in ("done", "cancelled", "paused", "blocked"):
        return {"goal": goal, "runs": [], "reason": f"goal is {goal['status']}"}

    bot = await get_active_bot(user_id)
    ready = await goal_service.ready_tasks(user_id, goal_id)
    runs = []
    for task in ready[: max(1, limit)]:
        if await _active_run(task["id"]):
            continue
        attempt = await _attempts(task["id"]) + 1
        run = await runner.create_run(
            user_id,
            bot,
            _task_prompt(goal, task),
            trigger="goal",
            goal_id=goal_id,
            task_id=task["id"],
            agent_profile_key=task.get("agent_profile_key"),
            idempotency_key=f"goal:{goal_id}:task:{task['id']}:run:{attempt}",
            auto_start=True,
        )
        await goal_service.update_task(user_id, task["id"], status="running")
        runs.append(run)

    if runs:
        goal = await goal_service.update_goal(user_id, goal_id, status="running")
    return {"goal": goal, "runs": [{"id": r.id, "task_id": r.task_id} for r in runs]}
