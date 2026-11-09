"""Verifier Agent: check Task output against acceptance criteria."""

from __future__ import annotations

import json

from sqlalchemy import select

from ai.bots.models import Run
from ai.bots.registry import get_active_bot
from ai.cognition import goals as goal_service
from ai.llm import llm_json
from core.database.session import async_session
from core.logging import get_logger

log = get_logger(__name__)

_SYSTEM = (
    "你是验收 Agent。只根据 acceptance criteria 检查产物。"
    "不重写产物，不替执行者解释。只返回 JSON："
    '{"passed": true|false, "notes": ["..."]}。'
)


async def _latest_run(task_id: int) -> Run | None:
    async with async_session() as db:
        return (await db.execute(
            select(Run).where(Run.task_id == task_id).order_by(Run.id.desc()).limit(1)
        )).scalar_one_or_none()


async def verify_task(user_id: int, task_id: int) -> dict | None:
    task = await goal_service.get_task(user_id, task_id)
    if task is None:
        return None
    run = await _latest_run(task_id)
    output = (run.output if run is not None else "") or ""
    acceptance = task.get("acceptance")
    passed = bool(output.strip())
    notes: list[str] = []

    if output.strip():
        bot = None
        try:
            bot = await get_active_bot(user_id)
        except Exception:
            pass
        result = await llm_json(
            _SYSTEM,
            json.dumps({
                "task": {
                    "title": task.get("title"),
                    "description": task.get("description"),
                    "acceptance": acceptance,
                },
                "output": output[:8000],
            }, ensure_ascii=False, default=str),
            max_chars=10000,
            bot=bot,
        )
        if isinstance(result, dict) and isinstance(result.get("passed"), bool):
            passed = result["passed"]
            notes = [str(x) for x in (result.get("notes") or []) if str(x).strip()]

    updated_task = await goal_service.update_task(
        user_id,
        task_id,
        status="done" if passed else "failed",
        output={
            **(task.get("output") or {}),
            "verification": {"passed": passed, "notes": notes},
        },
    )
    goal = await goal_service.get_goal(user_id, task["goal_id"])
    if goal is not None:
        tasks = await goal_service.list_tasks(user_id, task["goal_id"])
        if all(t["status"] == "done" for t in tasks):
            await goal_service.update_goal(user_id, task["goal_id"], status="done")
        elif any(t["status"] == "failed" for t in tasks):
            await goal_service.update_goal(user_id, task["goal_id"], status="blocked")
    return {"task": updated_task, "passed": passed, "notes": notes}
