"""Meta-tools that let an agent discover and run its enabled Agent Skills."""

from __future__ import annotations

import json

from ai.mcp.core import MCPCallResponse, MCPContent, MCPTool


def _ok(text: str) -> MCPCallResponse:
    return MCPCallResponse(content=[MCPContent(text=text)])


def _err(text: str) -> MCPCallResponse:
    return MCPCallResponse(isError=True, content=[MCPContent(text=text)])


async def run_skill_tool(user_id: int, args: dict) -> dict:
    from ai.bots.context import (
        get_current_bot_id,
        get_current_run_id,
        get_current_session_id,
    )
    from ai.skills import runtime

    key = str(args.get("skill_key") or args.get("skill") or "").strip()
    if not key:
        return {"error": "skill_key is required"}
    bot_id = get_current_bot_id()
    if bot_id is None:
        return {"error": "no active bot context"}
    payload = args.get("input")
    if not isinstance(payload, dict):
        payload = {}
    try:
        result = await runtime.run_skill(
            user_id,
            bot_id,
            key,
            payload,
            parent_run_id=get_current_run_id(),
            session_id=get_current_session_id(),
        )
        return {"ok": True, **result}
    except Exception as exc:
        return {"error": str(exc)}


async def _current_bot(user_id: int):
    from ai.bots import registry
    from ai.bots.context import get_current_bot_id

    bot_id = get_current_bot_id()
    if bot_id is None:
        return None
    try:
        return await registry.get_active_bot(user_id, int(bot_id))
    except Exception:
        return None


def _score(query: str, skill) -> int:
    q = (query or "").strip().lower()
    if not q:
        return 0
    key = (skill.key or "").lower()
    name = (skill.name or "").lower()
    desc = (skill.description or "").lower()
    score = 0
    if q == key:
        score += 1000
    elif q in key:
        score += 600
    if q == name:
        score += 800
    elif q in name:
        score += 500
    if q in desc:
        score += 200
    for token in q.replace(",", " ").replace("，", " ").split():
        if token in key:
            score += 120
        if token in name:
            score += 80
        if token in desc:
            score += 40
    return score


async def skill_search(user_id: int, args: dict) -> MCPCallResponse:
    query = str(args.get("query") or "").strip()
    if not query:
        return _err("query 必填，例如 简报 / 复盘 / 会议")
    try:
        limit = int(args.get("limit") or 5)
    except (TypeError, ValueError):
        limit = 5
    limit = min(max(limit, 1), 20)

    from ai.skills import runtime

    bot = await _current_bot(user_id)
    if bot is None:
        return _err("没有激活的 Bot 上下文，无法检索技能")
    skills = await runtime.enabled_skills(bot)
    scored = [(_score(query, skill), skill) for skill in skills]
    scored = [item for item in scored if item[0] > 0]
    scored.sort(key=lambda item: (-item[0], item[1].key))
    items = [
        {
            "skill_key": skill.key,
            "name": skill.name,
            "description": skill.description,
            "inputs": skill.inputs,
            "outputs": skill.outputs,
            "allowed_tools": skill.allowed_tools,
            "scope": skill.scope,
        }
        for _, skill in scored[:limit]
    ]
    payload: dict = {"query": query, "skills": items}
    if not items:
        payload["hint"] = "没有匹配技能。换更短的关键词，或让用户在设置里启用相关技能。"
    return _ok(json.dumps(payload, ensure_ascii=False))


async def skill_call(user_id: int, args: dict) -> MCPCallResponse:
    key = str(args.get("skill_key") or args.get("skill") or "").strip()
    if not key:
        return _err("skill_key 必填；先调用 skill_search 获取")
    bot = await _current_bot(user_id)
    if bot is None:
        return _err("没有激活的 Bot 上下文，无法调用技能")
    from ai.skills import runtime

    enabled = {skill.key for skill in await runtime.enabled_skills(bot)}
    if key not in enabled:
        return _err(f"技能 {key} 不存在或未启用")
    payload = args.get("input")
    if not isinstance(payload, dict):
        payload = {}
    result = await run_skill_tool(user_id, {"skill_key": key, "input": payload})
    if isinstance(result, dict) and result.get("error"):
        return _err(str(result["error"]))
    return _ok(json.dumps(result, ensure_ascii=False))


TOOLS = [
    (
        MCPTool(
            name="skill_search",
            description=(
                "搜索当前 Bot 已启用的技能，返回 skill_key、描述和 input schema。"
                "技能不是工具：先用它发现技能，再用 skill_call 执行。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "关键词，例如 简报 / 复盘 / 会议",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多返回数量，默认 5，最大 20",
                    },
                },
                "required": ["query"],
            },
        ),
        skill_search,
    ),
    (
        MCPTool(
            name="skill_call",
            description=(
                "执行 skill_search 返回的技能。传 skill_key 和 input 对象。"
                "不要臆造技能 key；未检索到就先 skill_search。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "skill_key": {
                        "type": "string",
                        "description": "技能 key，例如 daily-brief",
                    },
                    "input": {
                        "type": "object",
                        "description": "技能输入参数，例如 {\"day\":\"2026-11-07\"}",
                    },
                },
                "required": ["skill_key"],
            },
        ),
        skill_call,
    ),
    # Legacy single tool, kept for existing checkpoints and direct API callers.
    (
        MCPTool(
            name="skill",
            description=(
                "Run one of the Bot's enabled Agent Skills by key. "
                "Prefer skill_search + skill_call."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "skill_key": {
                        "type": "string",
                        "description": "Skill key, e.g. daily-brief",
                    },
                    "input": {
                        "type": "object",
                        "description": "Skill input, e.g. {\"day\":\"2026-11-07\"}",
                    },
                },
                "required": ["skill_key"],
            },
        ),
        run_skill_tool,
    ),
]
