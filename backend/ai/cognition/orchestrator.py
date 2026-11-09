"""Deterministic goal tick: plan -> dispatch -> complete."""

from __future__ import annotations

from ai.cognition import goals as goal_service
from ai.cognition.dispatcher import dispatch_goal
from ai.cognition.planner import plan_goal


async def tick_goal(user_id: int, goal_id: int) -> dict | None:
    goal = await goal_service.get_goal(user_id, goal_id)
    if goal is None:
        return None
    if goal["status"] in ("done", "cancelled", "paused"):
        return {"goal": goal, "tasks": await goal_service.list_tasks(user_id, goal_id)}

    tasks = await goal_service.list_tasks(user_id, goal_id)
    if not tasks:
        plan_goal(user_id, goal_id)
        tasks = await goal_service.list_tasks(user_id, goal_id)

    if all(t["status"] == "done" for t in tasks) and tasks:
        goal = await goal_service.update_goal(user_id, goal_id, status="done")
        return {"goal": goal, "tasks": tasks}

    if any(t["status"] == "failed" for t in tasks):
        goal = await goal_service.update_goal(user_id, goal_id, status="blocked")
        return {"goal": goal, "tasks": tasks}

    active = any(t["status"] in ("running", "waiting_approval") for t in tasks)
    dispatched = await dispatch_goal(user_id, goal_id)
    tasks = await goal_service.list_tasks(user_id, goal_id)
    goal = await goal_service.get_goal(user_id, goal_id)
    return {
        "goal": goal,
        "tasks": tasks,
        "runs": (dispatched or {}).get("runs", []),
        "waiting": active,
    }
