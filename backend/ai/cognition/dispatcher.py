"""Dispatcher: map ready Tasks to Runs."""

from __future__ import annotations

from sqlalchemy import func, select

from ai.bots import runner
from ai.bots.models import Run
from ai.bots.registry import get_active_bot
from ai.coding.service import create_coding_run
from ai.cognition import goals as goal_service
from core.config.settings import settings
from core.database.session import async_session
from core.sessions import service as session_service


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


def _choose_agent(goal: dict, task: dict) -> str:
    context = goal.get("context") or {}
    payload = task.get("input") if isinstance(task.get("input"), dict) else {}
    hint = str(payload.get("agent") or task.get("agent_profile_key") or "").strip().lower()
    if hint in {"researcher", "verifier", "planner", "architect", "comms"}:
        return hint
    if hint in {"coder_builtin", "coder_opencode", "coding", "executor"}:
        if hint == "executor" and not context.get("project_path"):
            return "chat"
        engine = str(context.get("engine") or settings.coding_engine or "builtin").lower()
        return "coder_opencode" if engine == "opencode" else "coder_builtin"
    if context.get("project_path"):
        engine = str(context.get("engine") or settings.coding_engine or "builtin").lower()
        return "coder_opencode" if engine == "opencode" else "coder_builtin"
    return "chat"


async def _ensure_goal_session(user_id: int, goal: dict) -> str:
    session_id = goal.get("primary_session_id")
    if session_id:
        return str(session_id)
    session = await session_service.create_session(
        user_id,
        bot_id=goal.get("bot_id"),
        title=goal.get("title") or "Goal",
        objective=goal.get("description") or goal.get("title"),
    )
    session_id = session["session_id"]
    await goal_service.update_goal(user_id, goal["id"], primary_session_id=session_id)
    return session_id


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
    session_id = await _ensure_goal_session(user_id, goal)
    ready = await goal_service.ready_tasks(user_id, goal_id)
    runs = []
    for task in ready[: max(1, limit)]:
        if await _active_run(task["id"]):
            continue
        attempt = await _attempts(task["id"]) + 1
        agent = _choose_agent(goal, task)
        prompt = _task_prompt(goal, task)
        context = goal.get("context") or {}
        if agent in ("coder_builtin", "coder_opencode"):
            project = str(context.get("project_path") or "")
            if not project:
                await goal_service.update_task(
                    user_id, task["id"], status="failed",
                    output={"error": "coding task has no project_path"},
                )
                continue
            run = await create_coding_run(
                user_id,
                bot,
                project,
                prompt,
                branch=context.get("branch"),
                engine="opencode" if agent == "coder_opencode" else "builtin",
                session_id=session_id,
                goal_id=goal_id,
                task_id=task["id"],
            )
        else:
            run = await runner.create_run(
                user_id,
                bot,
                prompt,
                trigger="goal",
                goal_id=goal_id,
                task_id=task["id"],
                agent=agent,
                agent_profile_key=task.get("agent_profile_key"),
                session_id=session_id,
                idempotency_key=f"goal:{goal_id}:task:{task['id']}:run:{attempt}",
                auto_start=True,
            )
        await goal_service.update_task(user_id, task["id"], status="running")
        runs.append(run)

    if runs:
        goal = await goal_service.update_goal(user_id, goal_id, status="running")
    return {"goal": goal, "runs": [{"id": r.id, "task_id": r.task_id} for r in runs]}
