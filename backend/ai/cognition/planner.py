"""Planner Agent: turn a Goal into executable Tasks."""

from __future__ import annotations

import json

from ai.bots.registry import get_active_bot
from ai.cognition import goals as goal_service
from ai.cognition.agent_profiles import get_profile
from ai.cognition.situation import situation_prompt
from ai.llm import llm_json
from core.logging import get_logger

log = get_logger(__name__)

_SYSTEM = (
    "你是规划 Agent。把用户目标拆成 1-6 个可执行 Task。"
    "每个 Task 必须有 title、description、agent_profile_key、acceptance。"
    "agent_profile_key 只能是 researcher/architect/comms/executor/verifier。"
    "depends_on 是前置 Task 的数组下标。"
    "只返回 JSON：{\"tasks\":[{\"title\":\"...\",\"description\":\"...\","
    "\"agent_profile_key\":\"executor\",\"depends_on\":[],"
    "\"acceptance\":[\"...\"],\"risk\":\"suggest\"}]}。"
    "不要编造不存在的日期、人名或承诺。"
)


async def _fallback_tasks(goal: dict) -> list[dict]:
    title = goal.get("title") or "推进目标"
    return [
        {
            "title": f"分析并推进：{title}"[:200],
            "description": goal.get("description") or title,
            "agent_profile_key": "executor",
            "depends_on": [],
            "acceptance": ["给出可执行结果", "说明依据"],
            "risk": "suggest",
        }
    ]


async def plan_goal(user_id: int, goal_id: int, *, force: bool = False) -> dict | None:
    goal = await goal_service.get_goal(user_id, goal_id)
    if goal is None:
        return None
    existing = await goal_service.list_tasks(user_id, goal_id)
    if existing and not force:
        return {"goal": goal, "tasks": existing, "created": 0}

    bot = None
    try:
        bot = await get_active_bot(user_id)
    except Exception:
        pass

    situation = ""
    try:
        situation = await situation_prompt(user_id)
    except Exception:
        pass

    payload = {
        "goal": {
            "title": goal.get("title"),
            "description": goal.get("description"),
            "due_at": str(goal.get("due_at") or ""),
            "success_criteria": goal.get("success_criteria"),
        },
        "situation": situation,
    }
    result = await llm_json(
        _SYSTEM,
        json.dumps(payload, ensure_ascii=False, default=str),
        max_chars=6000,
        bot=bot,
    )
    raw_tasks = result.get("tasks") if isinstance(result, dict) else None
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raw_tasks = await _fallback_tasks(goal)

    await goal_service.update_goal(user_id, goal_id, status="planning")
    created = []
    index_to_id: dict[int, int] = {}
    for index, item in enumerate(raw_tasks[:6]):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        profile_key = str(item.get("agent_profile_key") or "executor")
        if get_profile(profile_key) is None:
            profile_key = "executor"
        task = await goal_service.create_task(
            user_id,
            goal_id,
            title=title,
            description=str(item.get("description") or ""),
            agent_profile_key=profile_key,
            acceptance=item.get("acceptance") if isinstance(item.get("acceptance"), list) else None,
            risk=str(item.get("risk") or "suggest"),
            input={"goal": goal.get("title")},
            sort_order=index,
            depends_on=[],
        )
        if task is not None:
            created.append(task)
            index_to_id[index] = task.id

    for index, item in enumerate(raw_tasks[:6]):
        if index not in index_to_id or not isinstance(item, dict):
            continue
        deps = item.get("depends_on")
        if not isinstance(deps, list):
            continue
        mapped = [
            index_to_id[int(dep)]
            for dep in deps
            if str(dep).isdigit() and int(dep) in index_to_id
        ]
        if mapped:
            await goal_service.update_task(user_id, index_to_id[index], depends_on=mapped)

    updated = await goal_service.update_goal(user_id, goal_id, status="ready")
    return {"goal": updated, "tasks": await goal_service.list_tasks(user_id, goal_id), "created": len(created)}
