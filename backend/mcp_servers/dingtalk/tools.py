"""DingTalk tools exposed through MCP.

Write tools never pass --yes unless the caller explicitly sets confirmed=true;
the Hub/Bot approval flow owns that decision.
"""

from __future__ import annotations

import json

from .dws_client import DwSError, run_dws


def _text(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _ok(value) -> str:
    return _text({"ok": True, "data": value})


def _err(message: str) -> str:
    return _text({"ok": False, "error": message})


TOOLS = [
    {
        "name": "health",
        "description": "检查钉钉 CLI 登录态与当前组织。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_messages",
        "description": "跨会话搜索钉钉消息，用于查上下文、找承诺、做会议准备。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "start": {"type": "string", "description": "开始时间 RFC3339，可选"},
                "end": {"type": "string", "description": "结束时间 RFC3339，可选"},
                "limit": {"type": "integer", "description": "每页数量 1-100，默认 50"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_unread",
        "description": "列出当前有未读消息的钉钉会话。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "最多返回会话数"},
                "exclude_muted": {"type": "boolean", "description": "排除免打扰会话"},
            },
        },
    },
    {
        "name": "recent_conversations",
        "description": "列出指定时间以来有新消息的单聊和群聊。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "开始时间 RFC3339，默认最近 24 小时"},
            },
        },
    },
    {
        "name": "send_message",
        "description": "发送钉钉消息。confirmed 必须由用户在明确确认后设为 true。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "姓名或群名/openConversationId"},
                "content": {"type": "string", "description": "消息内容"},
                "group": {"type": "boolean", "description": "true 表示发群，false 表示单聊"},
                "confirmed": {"type": "boolean", "description": "用户已明确确认发送"},
            },
            "required": ["target", "content"],
        },
    },
    {
        "name": "list_events",
        "description": "查询指定时间范围的钉钉日程。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "开始时间 RFC3339"},
                "end": {"type": "string", "description": "结束时间 RFC3339"},
            },
            "required": ["start", "end"],
        },
    },
    {
        "name": "create_event",
        "description": "创建钉钉日程。confirmed 必须由用户确认后设为 true。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start": {"type": "string", "description": "开始时间 RFC3339"},
                "end": {"type": "string", "description": "结束时间 RFC3339"},
                "attendees": {"type": "array", "items": {"type": "string"}, "description": "参会人姓名"},
                "location": {"type": "string"},
                "description": {"type": "string"},
                "confirmed": {"type": "boolean"},
            },
            "required": ["title", "start", "end"],
        },
    },
    {
        "name": "list_todos",
        "description": "列出我的未完成钉钉待办，或按关键词搜索。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "可选关键词"},
            },
        },
    },
    {
        "name": "create_todo",
        "description": "创建钉钉待办。confirmed 必须由用户确认后设为 true。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "due": {"type": "string", "description": "截止时间 RFC3339，可选"},
                "assignee": {"type": "string", "description": "指派给某人的姓名，可选"},
                "confirmed": {"type": "boolean"},
            },
            "required": ["title"],
        },
    },
]


async def call_tool(name: str, args: dict) -> dict:
    args = args or {}
    try:
        if name == "health":
            return {"content": [{"type": "text", "text": _ok(await run_dws(["auth", "status", "--format", "json"]))}]}

        if name == "search_messages":
            query = str(args.get("query") or "").strip()
            if not query:
                return _tool_err("query 必填")
            cmd = ["chat", "+search-msg", "--query", query,
                   "--limit", str(min(max(int(args.get("limit") or 50), 1), 100)),
                   "--page-all", "--no-reactions", "--format", "json"]
            if args.get("start"):
                cmd += ["--start", str(args["start"])]
            if args.get("end"):
                cmd += ["--end", str(args["end"])]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd, timeout=120))}]}

        if name == "list_unread":
            cmd = ["chat", "+unread-chats", "--format", "json"]
            if args.get("count"):
                cmd += ["--count", str(int(args["count"]))]
            if args.get("exclude_muted"):
                cmd += ["--exclude-muted"]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd))}]}

        if name == "recent_conversations":
            cmd = ["chat", "+recent-conversations", "--format", "json"]
            if args.get("start"):
                cmd += ["--start", str(args["start"])]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd, timeout=120))}]}

        if name == "send_message":
            target = str(args.get("target") or "").strip()
            content = str(args.get("content") or "").strip()
            if not target or not content:
                return _tool_err("target 和 content 必填")
            if not args.get("confirmed"):
                return {"content": [{"type": "text", "text": _text({
                    "confirmation_required": True,
                    "message": "发送钉钉消息需要用户确认；确认后以 confirmed=true 重新调用。",
                    "target": target, "content": content,
                })}]}
            if args.get("group"):
                cmd = ["chat", "+send-to-group", "--group", target, "--content", content,
                       "--format", "json", "--yes"]
            else:
                cmd = ["chat", "+dm", "--to", target, "--content", content,
                       "--format", "json", "--yes"]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd))}]}

        if name == "list_events":
            start, end = args.get("start"), args.get("end")
            if not start or not end:
                return _tool_err("start 和 end 必填")
            cmd = ["calendar", "event", "list", "--start", str(start), "--end", str(end),
                   "--format", "json"]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd, timeout=120))}]}

        if name == "create_event":
            title = str(args.get("title") or "").strip()
            start, end = args.get("start"), args.get("end")
            if not title or not start or not end:
                return _tool_err("title/start/end 必填")
            if not args.get("confirmed"):
                return {"content": [{"type": "text", "text": _text({
                    "confirmation_required": True,
                    "message": "创建日程需要用户确认；确认后以 confirmed=true 重新调用。",
                    "title": title, "start": start, "end": end,
                })}]}
            attendees: list[str] = []
            for person in args.get("attendees") or []:
                resolved = await run_dws(
                    ["aisearch", "person", "--query", str(person), "--dimension", "name", "--format", "json"]
                )
                uid = _find_user_id(resolved)
                if not uid:
                    return _tool_err(f"无法唯一解析参会人: {person}")
                attendees.append(uid)
            cmd = ["calendar", "event", "create", "--title", title,
                   "--start", str(start), "--end", str(end), "--format", "json"]
            if attendees:
                cmd += ["--attendees", ",".join(attendees)]
            if args.get("location"):
                cmd += ["--location", str(args["location"])]
            if args.get("description"):
                cmd += ["--desc", str(args["description"])]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd, timeout=120))}]}

        if name == "list_todos":
            query = str(args.get("query") or "").strip()
            if query:
                cmd = ["todo", "+search", "--query", query, "--format", "json"]
            else:
                cmd = ["todo", "+get-my-tasks", "--all", "--status", "false", "--format", "json"]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd, timeout=120))}]}

        if name == "create_todo":
            title = str(args.get("title") or "").strip()
            if not title:
                return _tool_err("title 必填")
            if not args.get("confirmed"):
                return {"content": [{"type": "text", "text": _text({
                    "confirmation_required": True,
                    "message": "创建待办需要用户确认；确认后以 confirmed=true 重新调用。",
                    "title": title,
                })}]}
            assignee = str(args.get("assignee") or "").strip()
            if assignee:
                cmd = ["todo", "+assign", "--to", assignee, "--task", title, "--format", "json", "--yes"]
            else:
                cmd = ["todo", "+remind", "--task", title, "--format", "json", "--yes"]
                if args.get("due"):
                    cmd += ["--at", str(args["due"])]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd))}]}

        return _tool_err(f"未知工具: {name}")
    except DwSError as e:
        return _tool_err(str(e))
    except Exception as e:
        return _tool_err(f"{type(e).__name__}: {e}")


def _tool_err(message: str) -> dict:
    return {"content": [{"type": "text", "text": _err(message)}], "isError": True}


def _find_user_id(payload: dict) -> str | None:
    """Best-effort extraction from aisearch person results."""
    def walk(value):
        if isinstance(value, dict):
            for key in ("userId", "userid", "openDingTalkId", "openId"):
                if value.get(key):
                    return str(value[key])
            for child in value.values():
                found = walk(child)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = walk(child)
                if found:
                    return found
        return None

    return walk(payload)
