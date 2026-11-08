"""DingTalk tools exposed through MCP.

The CLI has far more services than we can model one-by-one, so common
workflows have typed tools and ``dws_cli`` provides a guarded passthrough for
the remaining business services.

Write tools never pass ``--yes`` unless the caller explicitly sets
``confirmed=true``; the Hub/Bot approval flow owns that decision.
"""

from __future__ import annotations

import json
import shlex

from .dws_client import DwSError, run_dws, run_dws_text


def _text(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _ok(value) -> str:
    return _text({"ok": True, "data": value})


def _err(message: str) -> str:
    return _text({"ok": False, "error": message})


def _tool_err(message: str) -> dict:
    return {"content": [{"type": "text", "text": _err(message)}], "isError": True}


def _s(value, default: str = "") -> str:
    return str(value if value is not None else default).strip()


def _i(value, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(number, high))


def _items(value, limit: int = 100) -> list[str]:
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, list):
        parts = value
    else:
        return []
    result = []
    for part in parts:
        text = _s(part)
        if text:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _confirmation(message: str, **fields) -> dict:
    return {"content": [{"type": "text", "text": _text({
        "confirmation_required": True,
        "message": message,
        **fields,
    })}]}


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
        "name": "list_chats",
        "description": "列出我加入的钉钉群聊或单聊，可按最近活跃排序。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "types": {"type": "string", "description": "group、p2p 或 group,p2p，默认 group"},
                "limit": {"type": "integer", "description": "每页数量 1-100，默认 50"},
                "page_all": {"type": "boolean", "description": "是否自动翻完所有分页"},
                "exclude_muted": {"type": "boolean", "description": "排除免打扰会话"},
                "sort": {"type": "string", "description": "create_time 或 active_time，可选"},
            },
        },
    },
    {
        "name": "list_chat_messages",
        "description": "读取指定群聊或单聊的消息记录，支持时间范围、发送人和排序。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string", "description": "群的 openConversationId"},
                "group": {"type": "string", "description": "群名或 openConversationId"},
                "open_dingtalk_id": {"type": "string", "description": "单聊对方的 openDingTalkId"},
                "start": {"type": "string", "description": "开始时间，可选；与 end 同时提供"},
                "end": {"type": "string", "description": "结束时间，可选；与 start 同时提供"},
                "sender": {"type": "string", "description": "发送人姓名或 userId，可选"},
                "order": {"type": "string", "description": "asc 或 desc，默认 asc"},
                "limit": {"type": "integer", "description": "最多消息数 1-500，默认 50"},
                "include_reactions": {"type": "boolean", "description": "是否包含表情回复"},
            },
        },
    },
    {
        "name": "at_me",
        "description": "查看最近 N 天群里或单聊里 @我 的消息。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "回溯天数 1-3650，默认 7"},
                "group": {"type": "string", "description": "仅查看指定群，可选"},
                "limit": {"type": "integer", "description": "每页数量，默认 50"},
                "page_all": {"type": "boolean", "description": "是否自动翻页"},
                "include_reactions": {"type": "boolean", "description": "是否包含表情回复"},
            },
        },
    },
    {
        "name": "list_chat_members",
        "description": "查看群成员，并区分真人与机器人。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "group": {"type": "string", "description": "群名或 openConversationId"},
                "conversation_id": {"type": "string", "description": "群 openConversationId"},
                "member_types": {"type": "string", "description": "user、bot 或 user,bot，默认全部"},
                "single_page": {"type": "boolean", "description": "只读一页用户成员"},
            },
        },
    },
    {
        "name": "conversation_info",
        "description": "查看群聊或单聊的名称、类型、成员数等基础信息。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "group": {"type": "string", "description": "群 openConversationId"},
                "open_dingtalk_id": {"type": "string", "description": "单聊对方 openDingTalkId"},
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
        "name": "search_contacts",
        "description": "按姓名、花名或部分名字搜索企业通讯录，返回 userId 和部门。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "姓名或关键词"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_contact",
        "description": "按姓名一步查询某人的完整通讯录资料。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "姓名/花名"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "my_profile",
        "description": "查看我自己的 userId、姓名、部门、组织和邮箱。",
        "inputSchema": {"type": "object", "properties": {}},
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
        "name": "free_busy",
        "description": "查询人员或会议室在指定时间段的忙闲。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "开始时间 ISO-8601"},
                "end": {"type": "string", "description": "结束时间 ISO-8601"},
                "users": {"type": "array", "items": {"type": "string"}, "description": "userId 列表"},
                "rooms": {"type": "array", "items": {"type": "string"}, "description": "roomId 列表"},
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
        "name": "update_event",
        "description": "更新日程标题、时间、地点、描述或参会人。confirmed 必须为 true。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "日程 eventId"},
                "title": {"type": "string"},
                "start": {"type": "string", "description": "新开始时间，与 end 同时提供"},
                "end": {"type": "string", "description": "新结束时间，与 start 同时提供"},
                "description": {"type": "string"},
                "location": {"type": "string"},
                "timezone": {"type": "string", "description": "IANA 时区"},
                "free_busy": {"type": "string", "description": "busy 或 free"},
                "add_attendees": {"type": "array", "items": {"type": "string"}, "description": "新增参会人 userId"},
                "remove_attendees": {"type": "array", "items": {"type": "string"}, "description": "移除参会人 userId"},
                "confirmed": {"type": "boolean"},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "cancel_event",
        "description": "取消一个已有日程。这是删除操作，confirmed 必须为 true。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "日程 eventId"},
                "confirmed": {"type": "boolean"},
            },
            "required": ["event_id"],
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
    {
        "name": "update_todo",
        "description": "修改待办标题、截止时间或优先级。confirmed 必须为 true。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "待办 taskId"},
                "title": {"type": "string"},
                "due": {"type": "string", "description": "ISO8601 截止时间"},
                "priority": {"type": "integer", "description": "10/20/30/40"},
                "confirmed": {"type": "boolean"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "complete_todo",
        "description": "完成一条待办。confirmed 必须为 true。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "待办 taskId"},
                "confirmed": {"type": "boolean"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "dws_cli",
        "description": (
            "钉钉 CLI 通用入口，用于调用尚未封装成专用工具的业务能力，例如 "
            "doc/drive/wiki/sheet/whiteboard/oa/report/minutes/attendance/ding/mail/"
            "aitable/agoal/contract/recruit/hrbrain/audit。args 是不含 dws 的参数数组，"
            "例如 [\"doc\",\"+list\"] 或 [\"oa\",\"approval\",\"list\"]。"
            "不确定参数时先运行 [\"help\",\"<service>\"] 或 [\"schema\",\"--cli-path\",\"<path>\"]。"
            "不要传 --yes、--profile、--client-secret；删除/取消类命令会被拒绝。"
            "写操作必须经用户确认后设置 confirmed=true。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "完整参数数组，例如 [\"chat\",\"+chat-list\",\"--types\",\"group,p2p\"]",
                },
                "command": {
                    "type": "string",
                    "description": "可选：单个命令行字符串（支持引号），与 args 二选一",
                },
                "confirmed": {
                    "type": "boolean",
                    "description": "写操作经用户明确确认后设为 true",
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数，默认 90，最大 300",
                },
            },
        },
    },
]


# Services safe to reach through the generic passthrough. Credential,
# developer and raw-API namespaces stay out of reach on purpose.
_ALLOWED_SERVICES = {
    "help", "schema",
    "chat", "calendar", "todo", "contact", "aisearch", "attendance",
    "doc", "drive", "sheet", "wiki", "whiteboard", "minutes", "report",
    "oa", "ding", "mail", "live", "agoal", "aitable", "contract",
    "recruit", "hrbrain", "audit",
}
_BLOCKED_FLAG_PREFIXES = (
    "--yes", "-y", "--client-id", "--client-secret", "--profile",
    "--mock", "--output", "--output-dir", "--overwrite",
)
_DESTRUCTIVE_WORDS = {
    "delete", "remove", "cancel", "revoke", "dismiss", "drop", "purge",
    "reject", "refuse", "destroy", "reset",
}
_WRITE_WORDS = {
    "create", "update", "write", "add", "send", "post", "reply", "forward",
    "assign", "complete", "close", "reopen", "approve", "agree", "invite",
    "respond", "rsvp", "set", "mark", "move", "rename", "share", "upload",
    "pin", "unpin", "remind", "comment", "submit", "publish", "enable",
    "disable", "book", "broadcast", "modify", "edit", "import", "export",
}
_READ_SHORTCUTS = {
    "at-me", "chat-list", "chat-messages", "chat-members-list",
    "chat-group-members", "conversation-info", "conversation-list-top",
    "feed-group-query-item", "flag-list", "search-msg", "unread-chats",
    "recent-conversations", "agenda", "attendee-list", "book-list",
    "book-search", "conflicts", "free", "free-slots", "freebusy",
    "my-free", "next-event", "room-find", "room-groups", "room-search",
    "search-event", "suggest-time", "suggestion", "today", "tomorrow",
    "week", "get", "get-my-tasks", "get-related-tasks", "get-created-todos",
    "created-todos", "due-today", "overdue", "list-attachment",
    "list-comment", "list-sub", "search", "lookup", "by-mobile", "me",
    "org", "team", "resolve-dept", "dept-members", "list-dept-members",
    "list-followings", "list-role-members", "list-roles", "list-sub-depts",
    "search-mobile", "search-user", "search-person",
}
_READ_WORDS = {
    "list", "get", "search", "info", "query", "read", "status", "history",
    "today", "tomorrow", "week", "agenda", "free", "freebusy", "conflicts",
    "suggestion", "suggest", "lookup", "me", "team", "members", "member",
    "recent", "unread", "find", "due", "overdue", "related", "created",
    "attachment", "comment", "sub", "roles", "followings", "self",
    "get-self", "search-mobile", "search-user", "search-person",
}


def _path_tokens(argv: list[str]) -> list[str]:
    path = []
    for token in argv[1:]:
        if token.startswith("-"):
            break
        path.append(token.lower())
    return path


def _classify(argv: list[str]) -> str:
    """Return ``read``, ``write`` or ``destructive`` for a dws argv."""
    if argv and argv[0].lower() in {"help", "schema"}:
        return "read"
    path = _path_tokens(argv)
    for token in path:
        clean = token.lstrip("+").replace("_", "-")
        parts = clean.split("-")
        if clean in _DESTRUCTIVE_WORDS or any(word in parts for word in _DESTRUCTIVE_WORDS):
            return "destructive"
    for token in path:
        clean = token.lstrip("+").replace("_", "-")
        parts = clean.split("-")
        if clean in _WRITE_WORDS or any(word in parts for word in _WRITE_WORDS):
            return "write"
    for token in path:
        short = token.lstrip("+")
        if token.startswith("+") and short in _READ_SHORTCUTS:
            return "read"
        parts = short.replace("_", "-").split("-")
        if any(part in _READ_WORDS for part in parts):
            return "read"
        if short in _READ_WORDS:
            return "read"
    return "write"


def _normalise_argv(args: dict) -> list[str]:
    raw = args.get("args")
    if isinstance(raw, str):
        argv = shlex.split(raw)
    elif isinstance(raw, list):
        argv = [_s(item) for item in raw]
    elif args.get("command"):
        argv = shlex.split(str(args.get("command") or ""))
    else:
        return []
    argv = [item for item in argv if item]
    if argv and argv[0].lower() in {"dws", "dws.exe"}:
        argv = argv[1:]
    return argv


async def call_tool(name: str, args: dict) -> dict:
    args = args or {}
    try:
        if name == "health":
            return {"content": [{"type": "text", "text": _ok(await run_dws(["auth", "status", "--format", "json"]))}]}

        if name == "search_messages":
            query = _s(args.get("query"))
            if not query:
                return _tool_err("query 必填")
            cmd = ["chat", "+search-msg", "--query", query,
                   "--limit", str(_i(args.get("limit"), 50, 1, 100)),
                   "--page-all", "--no-reactions", "--format", "json"]
            if args.get("start"):
                cmd += ["--start", _s(args["start"])]
            if args.get("end"):
                cmd += ["--end", _s(args["end"])]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd, timeout=120))}]}

        if name == "list_unread":
            cmd = ["chat", "+unread-chats", "--format", "json"]
            if args.get("count"):
                cmd += ["--count", str(_i(args.get("count"), 20, 1, 100))]
            if args.get("exclude_muted"):
                cmd += ["--exclude-muted"]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd))}]}

        if name == "recent_conversations":
            cmd = ["chat", "+recent-conversations", "--format", "json"]
            if args.get("start"):
                cmd += ["--start", _s(args["start"])]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd, timeout=120))}]}

        if name == "list_chats":
            types = _s(args.get("types")) or "group"
            kinds = {item.strip() for item in types.split(",") if item.strip()}
            if not kinds or not kinds <= {"group", "p2p"}:
                return _tool_err("types 只能包含 group 和/或 p2p")
            cmd = ["chat", "+chat-list", "--types", ",".join(sorted(kinds)),
                   "--page-size", str(_i(args.get("limit"), 50, 1, 100)),
                   "--format", "json"]
            if args.get("page_all"):
                cmd += ["--page-all", "--page-limit", "50"]
            if args.get("exclude_muted"):
                cmd += ["--exclude-muted"]
            if _s(args.get("sort")) in {"create_time", "active_time"}:
                cmd += ["--sort", _s(args.get("sort"))]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd, timeout=120))}]}

        if name == "list_chat_messages":
            conversation_id = _s(args.get("conversation_id"))
            group = _s(args.get("group"))
            open_id = _s(args.get("open_dingtalk_id"))
            if sum(bool(item) for item in (conversation_id, group, open_id)) != 1:
                return _tool_err("conversation_id / group / open_dingtalk_id 必须且只能指定一个")
            start, end = _s(args.get("start")), _s(args.get("end"))
            if bool(start) != bool(end):
                return _tool_err("start 和 end 必须同时提供")
            limit = _i(args.get("limit"), 50, 1, 500)
            if conversation_id:
                cmd = ["chat", "+chat-messages", "--conversation-id", conversation_id]
            elif group:
                cmd = ["chat", "+chat-messages", "--group", group]
            else:
                cmd = ["chat", "+chat-messages", "--open-dingtalk-id", open_id]
            if start:
                cmd += ["--start", start, "--end", end]
            order = _s(args.get("order")).lower() or "asc"
            cmd += ["--order", "desc" if order == "desc" else "asc"]
            if _s(args.get("sender")):
                cmd += ["--sender", _s(args.get("sender"))]
            if limit <= 100:
                cmd += ["--limit", str(limit)]
            else:
                cmd += ["--page-all", "--page-limit", "50", "--max-items", str(limit)]
            if not args.get("include_reactions"):
                cmd += ["--no-reactions"]
            cmd += ["--format", "json"]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd, timeout=180))}]}

        if name == "at_me":
            cmd = ["chat", "+at-me", "--days", str(_i(args.get("days"), 7, 1, 3650)),
                   "--limit", str(_i(args.get("limit"), 50, 1, 100)), "--format", "json"]
            if _s(args.get("group")):
                cmd += ["--group", _s(args.get("group"))]
            if args.get("page_all"):
                cmd += ["--page-all", "--page-limit", "50"]
            if not args.get("include_reactions"):
                cmd += ["--no-reactions"]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd, timeout=120))}]}

        if name == "list_chat_members":
            group = _s(args.get("group"))
            conversation_id = _s(args.get("conversation_id"))
            if bool(group) == bool(conversation_id):
                return _tool_err("group / conversation_id 必须且只能指定一个")
            member_types = _s(args.get("member_types")) or "user,bot"
            kinds = {item.strip() for item in member_types.split(",") if item.strip()}
            if not kinds <= {"user", "bot"}:
                return _tool_err("member_types 只能包含 user 和/或 bot")
            cmd = ["chat", "+chat-members-list"]
            cmd += ["--group", group] if group else ["--conversation-id", conversation_id]
            cmd += ["--member-types", ",".join(sorted(kinds)), "--page-limit", "50", "--format", "json"]
            if args.get("single_page"):
                cmd += ["--single-page"]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd, timeout=120))}]}

        if name == "conversation_info":
            group = _s(args.get("group"))
            open_id = _s(args.get("open_dingtalk_id"))
            if bool(group) == bool(open_id):
                return _tool_err("group / open_dingtalk_id 必须且只能指定一个")
            cmd = ["chat", "+conversation-info"]
            cmd += ["--group", group] if group else ["--open-dingtalk-id", open_id]
            cmd += ["--format", "json"]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd))}]}

        if name == "send_message":
            target = _s(args.get("target"))
            content = _s(args.get("content"))
            if not target or not content:
                return _tool_err("target 和 content 必填")
            if not args.get("confirmed"):
                return _confirmation(
                    "发送钉钉消息需要用户确认；确认后以 confirmed=true 重新调用。",
                    target=target, content=content,
                )
            if args.get("group"):
                cmd = ["chat", "+send-to-group", "--group", target, "--content", content,
                       "--format", "json", "--yes"]
            else:
                cmd = ["chat", "+dm", "--to", target, "--content", content,
                       "--format", "json", "--yes"]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd))}]}

        if name == "search_contacts":
            query = _s(args.get("query"))
            if not query:
                return _tool_err("query 必填")
            return {"content": [{"type": "text", "text": _ok(await run_dws(
                ["contact", "+search-user", "--query", query, "--format", "json"], timeout=60
            ))}]}

        if name == "get_contact":
            person = _s(args.get("name"))
            if not person:
                return _tool_err("name 必填")
            return {"content": [{"type": "text", "text": _ok(await run_dws(
                ["contact", "+lookup", "--name", person, "--format", "json"], timeout=60
            ))}]}

        if name == "my_profile":
            return {"content": [{"type": "text", "text": _ok(await run_dws(
                ["contact", "+me", "--format", "json"], timeout=60
            ))}]}

        if name == "list_events":
            start, end = _s(args.get("start")), _s(args.get("end"))
            if not start or not end:
                return _tool_err("start 和 end 必填")
            cmd = ["calendar", "event", "list", "--start", start, "--end", end,
                   "--format", "json"]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd, timeout=120))}]}

        if name == "free_busy":
            start, end = _s(args.get("start")), _s(args.get("end"))
            users = _items(args.get("users"))
            rooms = _items(args.get("rooms"))
            if not start or not end:
                return _tool_err("start 和 end 必填")
            if not users and not rooms:
                return _tool_err("users 和 rooms 至少提供一个")
            cmd = ["calendar", "+freebusy", "--start", start, "--end", end]
            if users:
                cmd += ["--users", ",".join(users)]
            if rooms:
                cmd += ["--rooms", ",".join(rooms)]
            cmd += ["--format", "json"]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd, timeout=120))}]}

        if name == "create_event":
            title = _s(args.get("title"))
            start, end = _s(args.get("start")), _s(args.get("end"))
            if not title or not start or not end:
                return _tool_err("title/start/end 必填")
            if not args.get("confirmed"):
                return _confirmation(
                    "创建日程需要用户确认；确认后以 confirmed=true 重新调用。",
                    title=title, start=start, end=end,
                )
            attendees: list[str] = []
            for person in args.get("attendees") or []:
                resolved = await run_dws(
                    ["aisearch", "person", "--query", str(person),
                     "--dimension", "name", "--format", "json"]
                )
                uid = _find_user_id(resolved)
                if not uid:
                    return _tool_err(f"无法唯一解析参会人: {person}")
                attendees.append(uid)
            cmd = ["calendar", "event", "create", "--title", title,
                   "--start", start, "--end", end, "--format", "json", "--yes"]
            if attendees:
                cmd += ["--attendees", ",".join(attendees)]
            if args.get("location"):
                cmd += ["--location", _s(args["location"])]
            if args.get("description"):
                cmd += ["--desc", _s(args["description"])]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd, timeout=120))}]}

        if name == "update_event":
            event_id = _s(args.get("event_id"))
            if not event_id:
                return _tool_err("event_id 必填")
            start, end = _s(args.get("start")), _s(args.get("end"))
            if bool(start) != bool(end):
                return _tool_err("start 和 end 必须同时提供")
            fields = {
                "title": _s(args.get("title")),
                "desc": _s(args.get("description")),
                "location": _s(args.get("location")),
                "timezone": _s(args.get("timezone")),
            }
            free_busy = _s(args.get("free_busy")).lower()
            if free_busy and free_busy not in {"busy", "free"}:
                return _tool_err("free_busy 只能是 busy 或 free")
            add = _items(args.get("add_attendees"))
            remove = _items(args.get("remove_attendees"))
            if not any(fields.values()) and not (start and end) and not free_busy and not add and not remove:
                return _tool_err("至少提供一项要修改的字段")
            if not args.get("confirmed"):
                return _confirmation(
                    "更新日程需要用户确认；确认后以 confirmed=true 重新调用。",
                    event_id=event_id,
                )
            cmd = ["calendar", "+update", "--event", event_id]
            for flag, value in (("--title", fields["title"]), ("--desc", fields["desc"]),
                                ("--location", fields["location"]),
                                ("--timezone", fields["timezone"])):
                if value:
                    cmd += [flag, value]
            if start and end:
                cmd += ["--start", start, "--end", end]
            if free_busy:
                cmd += ["--free-busy", free_busy]
            if add:
                cmd += ["--add-attendees", ",".join(add)]
            if remove:
                cmd += ["--remove-attendees", ",".join(remove)]
            cmd += ["--format", "json", "--yes"]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd, timeout=120))}]}

        if name == "cancel_event":
            event_id = _s(args.get("event_id"))
            if not event_id:
                return _tool_err("event_id 必填")
            if not args.get("confirmed"):
                return _confirmation(
                    "取消日程会真实删除该日程，需要用户确认；确认后以 confirmed=true 重新调用。",
                    event_id=event_id,
                )
            cmd = ["calendar", "+cancel-event", "--event", event_id,
                   "--format", "json", "--yes"]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd, timeout=120))}]}

        if name == "list_todos":
            query = _s(args.get("query"))
            if query:
                cmd = ["todo", "+search", "--query", query, "--format", "json"]
            else:
                cmd = ["todo", "+get-my-tasks", "--all", "--status", "false", "--format", "json"]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd, timeout=120))}]}

        if name == "create_todo":
            title = _s(args.get("title"))
            if not title:
                return _tool_err("title 必填")
            if not args.get("confirmed"):
                return _confirmation(
                    "创建待办需要用户确认；确认后以 confirmed=true 重新调用。",
                    title=title,
                )
            assignee = _s(args.get("assignee"))
            if assignee:
                cmd = ["todo", "+assign", "--to", assignee, "--task", title,
                       "--format", "json", "--yes"]
            else:
                cmd = ["todo", "+remind", "--task", title, "--format", "json", "--yes"]
                if args.get("due"):
                    cmd += ["--at", _s(args["due"])]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd))}]}

        if name == "update_todo":
            task_id = _s(args.get("task_id"))
            if not task_id:
                return _tool_err("task_id 必填")
            title = _s(args.get("title"))
            due = _s(args.get("due"))
            priority = args.get("priority")
            if not title and not due and priority is None:
                return _tool_err("title / due / priority 至少提供一个")
            if priority is not None and int(priority) not in {10, 20, 30, 40}:
                return _tool_err("priority 只能是 10/20/30/40")
            if not args.get("confirmed"):
                return _confirmation(
                    "修改待办需要用户确认；确认后以 confirmed=true 重新调用。",
                    task_id=task_id,
                )
            cmd = ["todo", "+update", "--task-id", task_id]
            if title:
                cmd += ["--title", title]
            if due:
                cmd += ["--due", due]
            if priority is not None:
                cmd += ["--priority", str(priority)]
            cmd += ["--format", "json", "--yes"]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd))}]}

        if name == "complete_todo":
            task_id = _s(args.get("task_id"))
            if not task_id:
                return _tool_err("task_id 必填")
            if not args.get("confirmed"):
                return _confirmation(
                    "完成待办需要用户确认；确认后以 confirmed=true 重新调用。",
                    task_id=task_id,
                )
            cmd = ["todo", "+complete", "--task-id", task_id,
                   "--format", "json", "--yes"]
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd))}]}

        if name == "dws_cli":
            argv = _normalise_argv(args)
            if not argv:
                return _tool_err("args 或 command 至少提供一个")
            if len(argv) > 40 or any(len(item) > 500 for item in argv):
                return _tool_err("命令参数过多或过长")
            if any("\n" in item or "\x00" in item for item in argv):
                return _tool_err("命令参数不能包含换行或空字符")
            service = argv[0].lower()
            if service not in _ALLOWED_SERVICES:
                return _tool_err(f"该服务不允许通过通用入口调用: {service}")
            if any(item == "--" or item.lower().startswith(_BLOCKED_FLAG_PREFIXES) for item in argv):
                return _tool_err("不允许传 --yes、--profile、--client-secret、--output 等参数")
            kind = _classify(argv)
            if kind == "destructive":
                return _tool_err("删除/取消类命令不允许通过通用入口执行，请使用对应专用工具或钉钉客户端")
            if kind == "write" and not args.get("confirmed"):
                return _confirmation(
                    "这是钉钉写操作，请向用户确认后以 confirmed=true 重新调用。",
                    command="dws " + " ".join(shlex.quote(item) for item in argv),
                )
            cmd = list(argv)
            if kind == "write":
                cmd.append("--yes")
            if not any(item in {"--format", "-f"} or item.startswith("--format=") for item in cmd):
                cmd += ["--format", "json"]
            timeout = _i(args.get("timeout"), 90, 5, 300)
            if service in {"help", "schema"}:
                raw = await run_dws_text(cmd, timeout=timeout)
                return {"content": [{"type": "text", "text": raw[:20000] or "(空输出)"}]}
            return {"content": [{"type": "text", "text": _ok(await run_dws(cmd, timeout=timeout))}]}

        return _tool_err(f"未知工具: {name}")
    except DwSError as e:
        return _tool_err(str(e))
    except Exception as e:
        return _tool_err(f"{type(e).__name__}: {e}")
