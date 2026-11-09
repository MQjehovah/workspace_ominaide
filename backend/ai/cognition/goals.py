"""Goal and Task persistence and state transitions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from ai.bots.registry import get_active_bot
from ai.cognition.models import Goal, Task
from core.database.session import async_session

GOAL_STATUSES = ("draft", "planning", "ready", "running", "waiting", "waiting_approval", "verifying", "blocked", "paused", "done", "failed", "cancelled")
TASK_STATUSES = ("pending", "ready", "running", "waiting_approval", "blocked", "done", "failed", "cancelled")


def _goal_out(row: Goal) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "bot_id": row.bot_id,
        "title": row.title,
        "description": row.description,
        "status": row.status,
        "priority": row.priority,
        "due_at": row.due_at,
        "success_criteria": row.success_criteria,
        "context": row.context,
        "workspace_id": row.workspace_id,
        "primary_session_id": row.primary_session_id,
        "origin_message_id": row.origin_message_id,
        "token_budget": row.token_budget,
        "cost_budget": row.cost_budget,
        "max_steps": row.max_steps,
        "max_runs": row.max_runs,
        "budget_used": row.budget_used,
        "next_wake_at": row.next_wake_at,
        "last_run_at": row.last_run_at,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "completed_at": row.completed_at,
    }


def _task_out(row: Task) -> dict:
    return {
        "id": row.id,
        "goal_id": row.goal_id,
        "parent_task_id": row.parent_task_id,
        "title": row.title,
        "description": row.description,
        "agent_profile_key": row.agent_profile_key,
        "status": row.status,
        "depends_on": row.depends_on,
        "acceptance": row.acceptance,
        "risk": row.risk,
        "input": row.input,
        "output": row.output,
        "sort_order": row.sort_order,
        "deadline": row.deadline,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


async def create_goal(
    user_id: int,
    *,
    title: str,
    description: str | None = None,
    bot_id: int | None = None,
    due_at: datetime | None = None,
    priority: int = 50,
    success_criteria: list | dict | None = None,
    context: dict | None = None,
    primary_session_id: str | None = None,
    origin_message_id: int | None = None,
    created_by: str = "user",
) -> Goal:
    if bot_id is None:
        try:
            bot_id = (await get_active_bot(user_id)).id
        except Exception:
            bot_id = None
    async with async_session() as db:
        row = Goal(
            user_id=user_id,
            bot_id=bot_id,
            title=title[:200],
            description=description,
            status="draft",
            priority=max(0, min(int(priority), 100)),
            due_at=due_at,
            success_criteria=success_criteria,
            context=context,
            primary_session_id=primary_session_id,
            origin_message_id=origin_message_id,
            created_by=created_by,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        from ai.cognition.workspace import ensure_workspace

        workspace = await ensure_workspace(user_id, row.id, bot_id=row.bot_id)
        if workspace is not None:
            row.workspace_id = workspace.id
        return row


async def list_goals(user_id: int, *, status: str | None = None, limit: int = 50) -> list[dict]:
    async with async_session() as db:
        q = select(Goal).where(Goal.user_id == user_id)
        if status and status != "all":
            q = q.where(Goal.status == status)
        rows = list((await db.execute(
            q.order_by(Goal.priority.desc(), Goal.id.desc()).limit(max(1, min(limit, 200)))
        )).scalars().all())
    return [_goal_out(row) for row in rows]


async def get_goal(user_id: int, goal_id: int) -> dict | None:
    async with async_session() as db:
        row = (await db.execute(
            select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
        )).scalar_one_or_none()
        return _goal_out(row) if row is not None else None


async def update_goal(user_id: int, goal_id: int, **values) -> dict | None:
    async with async_session() as db:
        row = (await db.execute(
            select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
        )).scalar_one_or_none()
        if row is None:
            return None
        for key, value in values.items():
            if hasattr(row, key):
                setattr(row, key, value)
        if values.get("status") == "done":
            row.completed_at = datetime.now()
        await db.commit()
        await db.refresh(row)
        return _goal_out(row)


async def create_task(
    user_id: int,
    goal_id: int,
    *,
    title: str,
    description: str | None = None,
    agent_profile_key: str | None = None,
    depends_on: list[int] | None = None,
    acceptance: list | dict | None = None,
    risk: str = "suggest",
    input: dict | None = None,
    sort_order: int = 0,
    deadline: datetime | None = None,
) -> Task | None:
    async with async_session() as db:
        goal = (await db.execute(
            select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
        )).scalar_one_or_none()
        if goal is None:
            return None
        row = Task(
            goal_id=goal_id,
            title=title[:200],
            description=description,
            agent_profile_key=agent_profile_key,
            status="pending",
            depends_on=depends_on or [],
            acceptance=acceptance,
            risk=risk,
            input=input,
            sort_order=sort_order,
            deadline=deadline,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row


async def list_tasks(user_id: int, goal_id: int) -> list[dict]:
    async with async_session() as db:
        goal = (await db.execute(
            select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
        )).scalar_one_or_none()
        if goal is None:
            return []
        rows = list((await db.execute(
            select(Task).where(Task.goal_id == goal_id).order_by(Task.sort_order, Task.id)
        )).scalars().all())
    return [_task_out(row) for row in rows]


async def get_task(user_id: int, task_id: int) -> dict | None:
    async with async_session() as db:
        row = (await db.execute(
            select(Task).join(Goal, Goal.id == Task.goal_id).where(
                Task.id == task_id,
                Goal.user_id == user_id,
            )
        )).scalar_one_or_none()
        return _task_out(row) if row is not None else None


async def update_task(user_id: int, task_id: int, **values) -> dict | None:
    async with async_session() as db:
        row = (await db.execute(
            select(Task).join(Goal, Goal.id == Task.goal_id).where(
                Task.id == task_id,
                Goal.user_id == user_id,
            )
        )).scalar_one_or_none()
        if row is None:
            return None
        for key, value in values.items():
            if hasattr(row, key):
                setattr(row, key, value)
        await db.commit()
        await db.refresh(row)
        return _task_out(row)


async def ready_tasks(user_id: int, goal_id: int) -> list[Task]:
    """Tasks whose dependencies are all done."""
    tasks = await list_tasks(user_id, goal_id)
    done = {t["id"] for t in tasks if t["status"] == "done"}
    return [
        t for t in tasks
        if t["status"] == "pending"
        and all(dep in done for dep in (t.get("depends_on") or []))
    ]
