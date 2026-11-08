"""Unified tool catalog: pinned exposure, search and gateway calls.

The LLM no longer receives every registered tool schema. It gets a small
pinned set plus two stable entry points:

    tool_search(query, scope?, source?, machine_id?, limit?)
    tool_call(tool_id, arguments, machine_id?)

``tool_call`` resolves the real underlying tool so risk approval still applies
to the actual operation, not to the gateway itself.
"""

from __future__ import annotations

import json
import re

from core.ai.mcp.core import MCPCallRequest, MCPCallResponse, MCPContent, MCPTool
from core.ai.mcp.registry import tool_registry
from core.bots import policy
from core.bots.context import get_current_bot_id
from core.config.settings import settings
from core.logging import get_logger

log = get_logger(__name__)

GATEWAY_TOOLS = {"tool_search", "tool_call"}
# Legacy gateway tools stay registered for compatibility but must not appear
# in search results, otherwise the model can bypass the unified entry point.
HIDDEN_FROM_SEARCH = GATEWAY_TOOLS | {
    "local_mcp_search",
    "local_mcp_call",
    # Legacy local file tools are replaced by the compact local_file tool.
    "local_list_dir",
    "local_read_file",
    "local_write_file",
    "local_grep",
    # Legacy single skill tool is replaced by skill_search / skill_call.
    "skill",
}

DEFAULT_PINNED_TOOLS = {
    "tool_search",
    "tool_call",
    "save_memory",
    "send_notification",
    "web_search",
    "web_fetch",
    "skill_search",
    "skill_call",
}

# All local machine tools are source="local". They are never exposed
# directly; use tool_search(scope="machine") to discover them.

GATEWAY_INSTRUCTION = (
    "可用工具很多，未直接列出的能力必须先调用 tool_search 检索，再用 tool_call 调用。"
    "不要臆造工具名或参数。"
    "所有 local_* 本地工具和本地 MCP 工具不在默认工具表中，必须先用 "
    "tool_search(scope=\"machine\") 或 scope=\"all\" 检索，再用 tool_call 调用。"
    "技能先用 skill_search 检索，再用 skill_call 调用。"
    "tool_call 的审批按底层真实工具执行。"
)

_LOCAL_PREFIX = "local:"
_ID_PREFIXES = ("builtin:", "plugin:", "mcp:")


def _ok(text: str) -> MCPCallResponse:
    return MCPCallResponse(content=[MCPContent(text=text)])


def _err(text: str) -> MCPCallResponse:
    return MCPCallResponse(isError=True, content=[MCPContent(text=text)])


def gateway_instruction() -> str | None:
    return GATEWAY_INSTRUCTION if settings.tool_gateway_enabled else None


def canonical_id(tool: MCPTool) -> str:
    return f"{tool.source}:{tool.name}"


async def _load_bot(user_id: int):
    from core.database.session import async_session
    from core.bots.models import Bot

    bot_id = get_current_bot_id()
    if not bot_id:
        return None
    async with async_session() as db:
        bot = await db.get(Bot, int(bot_id))
    if bot is None or bot.user_id != user_id:
        return None
    return bot


def _online_machine_ids(user_id: int | None) -> list[str]:
    if not user_id:
        return []
    from core.wschannel.hub import host_channel

    return host_channel.machine_ids(user_id)


def select_exposed_tools(
    tools: list[MCPTool],
    bot=None,
    allowed=None,
    user_id: int | None = None,
) -> list[MCPTool]:
    """Return the small set of tools sent to the LLM."""
    if user_id is None and bot is not None:
        user_id = getattr(bot, "user_id", None)
    if allowed is None and bot is not None:
        allowed = getattr(bot, "allowed_tools", None)
    if allowed is not None:
        allowed_set = set(allowed) | GATEWAY_TOOLS
        tools = [t for t in tools if t.name in allowed_set]
    if not settings.tool_gateway_enabled:
        return tools

    pinned = getattr(bot, "pinned_tools", None) if bot is not None else None
    if pinned is None:
        # Bots with an explicit allowlist keep those tools directly exposed.
        pinned = allowed if allowed is not None else DEFAULT_PINNED_TOOLS
    wanted = set(pinned) | GATEWAY_TOOLS
    # Local machine tools are search-only. Never expose them directly.
    return [
        t for t in tools if t.name in wanted and t.source != "local"
    ]


# Common Chinese terms mapped to English words used in tool names/descriptions.
_QUERY_SYNONYMS = {
    "邮件": ["email", "mail", "gmail"],
    "邮箱": ["email", "mail"],
    "日程": ["calendar", "schedule", "event"],
    "日历": ["calendar", "schedule", "event"],
    "文件": ["file", "document"],
    "文档": ["document", "docx", "ppt"],
    "待办": ["todo", "task"],
    "任务": ["task", "todo", "job"],
    "笔记": ["note"],
    "资讯": ["news", "source", "rss"],
    "新闻": ["news", "source", "rss"],
    "天气": ["weather"],
    "搜索": ["search", "find"],
    "查找": ["search", "find"],
    "浏览器": ["browser", "page", "web"],
    "网页": ["web", "url", "page", "fetch"],
    "代码": ["code", "coding", "git", "project"],
    "项目": ["project", "code"],
    "记忆": ["memory"],
    "通知": ["notification", "notify"],
    "设备": ["device", "home assistant", "light", "switch"],
    "智能家居": ["home assistant", "light", "switch", "device"],
    "音乐": ["music", "play"],
    "钉钉": ["dingtalk"],
    "联系人": ["contact"],
    "同事": ["contact", "people"],
    "文件系统": ["filesystem", "file"],
}


def _query_variants(query: str) -> list[str]:
    q = (query or "").strip().lower()
    if not q:
        return []
    variants = [q]
    for zh, terms in _QUERY_SYNONYMS.items():
        if zh in q:
            variants.extend(terms)
    return variants


def _score_term(term: str, tool: MCPTool) -> int:
    name = tool.name.lower()
    desc = (tool.description or "").lower()
    score = 0
    if term == name:
        score += 1000
    elif term in name:
        score += 600
    if term in desc:
        score += 200
    for token in re.split(r"[\s,;，；/]+", term):
        if not token:
            continue
        if token == name:
            score += 300
        elif token in name:
            score += 120
        if token in desc:
            score += 40
    return score


def _score(query: str, tool: MCPTool) -> int:
    return max(
        (_score_term(term, tool) for term in _query_variants(query)),
        default=0,
    )


def _tool_item(tool: MCPTool, bot=None) -> dict:
    risk = policy.resolve_risk(bot, tool.name)
    return {
        "tool_id": canonical_id(tool),
        "name": tool.name,
        "source": tool.source,
        "server": tool.server,
        "risk": risk,
        "description": tool.description,
        "input_schema": tool.inputSchema,
    }


def search_server_tools(
    user_id: int,
    query: str,
    *,
    source: str | None = None,
    limit: int = 5,
    bot=None,
) -> list[dict]:
    tools = tool_registry.get_tools(user_id=user_id)
    allowed = getattr(bot, "allowed_tools", None) if bot is not None else None
    if allowed is not None:
        tools = [t for t in tools if t.name in set(allowed) | GATEWAY_TOOLS]
    if source:
        tools = [t for t in tools if t.source == source]
        if source == "local" and not _online_machine_ids(user_id):
            tools = []
    else:
        # Local machine tools are injected dynamically; don't duplicate them
        # in the server catalog.
        tools = [t for t in tools if t.source != "local"]
    scored: list[tuple[int, MCPTool]] = []
    for tool in tools:
        if tool.name in HIDDEN_FROM_SEARCH:
            continue
        score = _score(query, tool)
        if score > 0:
            scored.append((score, tool))
    scored.sort(key=lambda item: (-item[0], item[1].name))
    return [_tool_item(tool, bot) for _, tool in scored[:limit]]


async def search_local_tools(
    user_id: int,
    query: str,
    *,
    limit: int = 5,
    machine_id: str | None = None,
) -> tuple[list[dict], str | None]:
    from core.ai.mcp.tools.local import _resolve_machine
    from core.wschannel import local_tools

    try:
        machine = _resolve_machine(user_id, {"machine_id": machine_id})
    except local_tools.LocalMachineError as exc:
        return [], str(exc)
    machine_name = local_tools.host_channel.machine_name(machine)
    result: list[dict] = []
    seen: set[str] = set()
    for term in _query_variants(query)[:3]:
        try:
            response = await local_tools.call_local(
                user_id,
                machine,
                "mcp_search",
                {"query": term, "limit": limit},
                timeout_seconds=60,
            )
        except local_tools.LocalMachineError as exc:
            return result, str(exc)
        if not response.get("ok"):
            return result, str(response.get("error") or "读取本地 MCP 失败")
        payload = response.get("result") or {}
        items = payload.get("tools") if isinstance(payload, dict) else []
        for item in items or []:
            server_id = str(item.get("server_id") or "").strip()
            name = str(item.get("name") or "").strip()
            if not server_id or not name:
                continue
            tool_id = f"{_LOCAL_PREFIX}{machine}:{server_id}:{name}"
            if tool_id in seen:
                continue
            seen.add(tool_id)
            result.append({
                "tool_id": tool_id,
                "name": name,
                "source": "local",
                "server": server_id,
                "server_name": str(item.get("server_name") or server_id),
                "machine_id": machine,
                "machine_name": machine_name,
                "risk": "exec",
                "description": item.get("description") or "",
                "input_schema": item.get("input_schema")
                or {"type": "object", "properties": {}},
            })
            if len(result) >= limit:
                return result, None
    return result, None

def parse_tool_id(tool_id: str, name: str | None = None) -> dict:
    raw = (tool_id or name or "").strip()
    if raw.startswith(_LOCAL_PREFIX):
        rest = raw[len(_LOCAL_PREFIX):]
        if ":" not in rest:
            # Registered local primitive, e.g. local:local_shell
            return {"kind": "server", "name": rest, "source": "local"}
        parts = rest.split(":", 2)
        if len(parts) != 3:
            return {"kind": "invalid", "raw": raw}
        return {
            "kind": "local",
            "machine_id": parts[0],
            "server_id": parts[1],
            "tool": parts[2],
        }
    for prefix in _ID_PREFIXES:
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break
    return {"kind": "server", "name": raw}


def display_target(name: str, arguments: dict | None) -> tuple[str, dict]:
    """Return the underlying tool name/args for approvals and run steps."""
    if name != "tool_call":
        return name, arguments or {}
    args = arguments or {}
    target = parse_tool_id(
        str(args.get("tool_id") or ""), str(args.get("name") or "")
    )
    call_args = args.get("arguments")
    if not isinstance(call_args, dict):
        call_args = args.get("args") if isinstance(args.get("args"), dict) else {}
    if target.get("kind") == "local":
        return (
            f"local_mcp:{target.get('server_id')}/{target.get('tool')}",
            call_args,
        )
    return target.get("name") or name, call_args


async def tool_search(user_id: int, args: dict) -> MCPCallResponse:
    query = str(args.get("query") or "").strip()
    if not query:
        return _err("query 必填，例如 邮件、日程、browser、github")
    try:
        limit = int(args.get("limit") or 5)
    except (TypeError, ValueError):
        limit = 5
    limit = min(max(limit, 1), 20)

    scope = str(args.get("scope") or "server").strip().lower()
    if scope in ("local", "mechine"):
        scope = "machine"
    if scope not in ("server", "machine", "all"):
        scope = "server"
    source = str(args.get("source") or "").strip().lower() or None
    if source == "local":
        scope = "machine"
        source = None
    machine_id = str(args.get("machine_id") or "").strip() or None

    bot = await _load_bot(user_id)
    allowed = getattr(bot, "allowed_tools", None) if bot is not None else None
    items: list[dict] = []
    seen: set[str] = set()
    local_error: str | None = None

    def add(new_items: list[dict]) -> None:
        for item in new_items:
            tool_id = item.get("tool_id") or ""
            if tool_id and tool_id not in seen:
                seen.add(tool_id)
                items.append(item)

    if scope in ("server", "all"):
        add(search_server_tools(user_id, query, source=source, limit=limit, bot=bot))

    if scope in ("machine", "all") and source not in ("builtin", "plugin", "mcp"):
        # Local primitives are registered but only discoverable here.
        local_items = search_server_tools(
            user_id, query, source="local", limit=limit, bot=bot
        )
        if allowed is not None:
            local_items = [i for i in local_items if i["name"] in allowed]
        add(local_items)

        # MCP servers running on the desktop.
        if allowed is None or "local_mcp_call" in allowed:
            mcp_items, local_error = await search_local_tools(
                user_id, query, limit=limit, machine_id=machine_id
            )
            add(mcp_items)

    items = items[:limit]
    payload: dict = {"query": query, "scope": scope, "tools": items}
    if local_error:
        payload["local_error"] = local_error
    if not items:
        payload["hint"] = (
            "没有匹配工具。换更短的关键词；本地机器工具和本地 MCP 需要 "
            "scope=machine 或 scope=all。"
        )
    return _ok(json.dumps(payload, ensure_ascii=False))

async def _bot_allows(user_id: int, name: str) -> bool:
    bot = await _load_bot(user_id)
    if bot is None:
        return True
    allowed = getattr(bot, "allowed_tools", None)
    return allowed is None or name in allowed


async def tool_call(user_id: int, args: dict) -> MCPCallResponse:
    tool_id = str(args.get("tool_id") or "").strip()
    name_arg = str(args.get("name") or "").strip()
    target = parse_tool_id(tool_id, name_arg)
    call_args = args.get("arguments")
    if not isinstance(call_args, dict):
        call_args = args.get("args") if isinstance(args.get("args"), dict) else {}

    if target["kind"] == "invalid":
        return _err(
            "tool_id 格式无效。本地 primitive：local:<tool>；"
            "本地 MCP：local:<machine_id>:<server_id>:<tool>"
        )

    if target["kind"] == "local":
        server_id = target["server_id"]
        tool_name = target["tool"]
        machine_id = str(args.get("machine_id") or target["machine_id"]).strip()
        if not machine_id or not server_id or not tool_name:
            return _err("本地工具需要 machine_id、server_id 和 tool")
        if not await _bot_allows(user_id, "local_mcp_call"):
            return _err("当前 Bot 不允许调用本地 MCP 工具")
        from core.wschannel import local_tools

        try:
            response = await local_tools.call_local(
                user_id,
                machine_id,
                "mcp_call",
                {
                    "server_id": server_id,
                    "tool": tool_name,
                    "arguments": call_args,
                },
                timeout_seconds=120,
            )
        except local_tools.LocalMachineError as exc:
            return _err(str(exc))
        if not response.get("ok"):
            return _err(str(response.get("error") or "本地 MCP 调用失败"))
        payload = response.get("result") or {}
        content = payload.get("content") if isinstance(payload, dict) else None
        text = content if isinstance(content, str) else json.dumps(
            content, ensure_ascii=False
        )
        if payload.get("is_error"):
            return _err(text or "本地 MCP 工具执行出错")
        return _ok(text or "(本地 MCP 返回空结果)")

    name = target.get("name") or ""
    if name in GATEWAY_TOOLS:
        return _err("不能通过 tool_call 调用工具网关本身")
    if name in HIDDEN_FROM_SEARCH:
        return _err(f"{name} 已由统一工具网关取代，请使用 tool_search / tool_call")
    if not await _bot_allows(user_id, name):
        return _err(f"当前 Bot 不允许调用工具 {name}")
    if tool_registry.get_handler(name) is None:
        return _err(f"工具不存在：{name}")
    return await tool_registry.call(
        user_id, MCPCallRequest(name=name, arguments=call_args)
    )


TOOLS = [
    (
        MCPTool(
            name="tool_search",
            description=(
                "搜索可用工具目录，返回工具 ID、描述和参数 schema。"
                "插件工具、服务端 MCP 用默认 scope=server；"
                "所有 local_* 本地工具和本地 MCP 必须 scope=machine 才能搜到。"
                "找到后必须用 tool_call 调用。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "关键词，例如 邮件 / 日程 / browser / github",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["server", "machine", "all"],
                        "description": (
                            "server=服务端工具（默认），machine=本地机器工具和本地 MCP，"
                            "all=两者。local 为 machine 的兼容别名。"
                        ),
                    },
                    "source": {
                        "type": "string",
                        "enum": ["builtin", "plugin", "mcp", "local"],
                        "description": "可选，按来源过滤；local 等同于 scope=machine",
                    },
                    "machine_id": {
                        "type": "string",
                        "description": "搜索本地机器工具时指定机器 ID",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多返回数量，默认 5，最大 20",
                    },
                },
                "required": ["query"],
            },
        ),
        tool_search,
    ),
    (
        MCPTool(
            name="tool_call",
            description=(
                "调用 tool_search 返回的工具。tool_id 使用搜索结果里的 ID。"
                "审批按底层真实工具的 risk 执行，而不是按 tool_call 本身。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "tool_id": {
                        "type": "string",
                        "description": "tool_search 返回的 tool_id",
                    },
                    "arguments": {
                        "type": "object",
                        "description": "传给底层工具的参数 JSON",
                    },
                    "machine_id": {
                        "type": "string",
                        "description": "本地工具可覆盖 machine_id",
                    },
                },
                "required": ["tool_id"],
            },
        ),
        tool_call,
    ),
]
