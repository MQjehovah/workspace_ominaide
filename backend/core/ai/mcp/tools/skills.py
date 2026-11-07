"""Meta-tool that lets an agent load and run one of its enabled Agent Skills."""

from __future__ import annotations

from core.ai.mcp.core import MCPTool


async def run_skill_tool(user_id: int, args: dict) -> dict:
    from core.bots.context import (
        get_current_bot_id,
        get_current_run_id,
        get_current_session_id,
    )
    from core.skills import runtime

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


TOOLS = [
    (
        MCPTool(
            name="skill",
            description=(
                "Run one of the Bot's enabled Agent Skills by key. "
                "Available skills are listed in the system prompt. "
                "Pass skill_key and an input object; the skill returns structured output."
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
    )
]
