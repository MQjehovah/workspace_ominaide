"""Google external authorization plugin tools (Gmail, Calendar, Drive)."""

from __future__ import annotations

import mimetypes

from ai.mcp.core import MCPCallResponse, MCPContent, MCPTool
from plugins.oauth.backend import service


def _ok(text: str) -> MCPCallResponse:
    return MCPCallResponse(content=[MCPContent(text=text)])


def _err(text: str) -> MCPCallResponse:
    return MCPCallResponse(isError=True, content=[MCPContent(text=text)])


async def _token(user_id: int, args: dict) -> tuple[str, int | None]:
    try:
        account_id = int(args["account_id"]) if args.get("account_id") else None
    except (TypeError, ValueError):
        account_id = None
    token, account = await service.get_access_token(user_id, "google", account_id)
    return token, account.id


async def google_gmail_search(user_id: int, args: dict) -> MCPCallResponse:
    query = str(args.get("query") or "").strip()
    if not query:
        return _err("query 必填")
    try:
        token, _ = await _token(user_id, args)
        from plugins.oauth.backend import google

        rows = await google.gmail_search(
            token, query, int(args.get("limit") or 10)
        )
    except Exception as exc:
        return _err(str(exc))
    lines = [f"Gmail 搜索结果（{len(rows)}）："]
    for row in rows:
        lines.append(
            f"- {row.get('date')} · {row.get('from')} · {row.get('subject')}\n"
            f"  id={row.get('id')} · {row.get('snippet')}"
        )
    return _ok("\n".join(lines))


async def google_gmail_read(user_id: int, args: dict) -> MCPCallResponse:
    message_id = str(args.get("message_id") or "").strip()
    if not message_id:
        return _err("message_id 必填")
    try:
        token, _ = await _token(user_id, args)
        from plugins.oauth.backend import google

        message = await google.gmail_read(token, message_id)
    except Exception as exc:
        return _err(str(exc))
    return _ok(
        f"From: {message['from']}\n"
        f"To: {message['to']}\n"
        f"Subject: {message['subject']}\n"
        f"Date: {message['date']}\n\n"
        f"{message['body']}"
    )


async def google_gmail_send(user_id: int, args: dict) -> MCPCallResponse:
    to = str(args.get("to") or "").strip()
    subject = str(args.get("subject") or "").strip()
    body = str(args.get("body") or "")
    if not to or not subject:
        return _err("to 和 subject 必填")
    try:
        token, _ = await _token(user_id, args)
        from plugins.oauth.backend import google

        result = await google.gmail_send(
            token,
            to=to,
            subject=subject,
            body=body,
            cc=str(args.get("cc") or "").strip() or None,
        )
    except Exception as exc:
        return _err(str(exc))
    return _ok(f"邮件已发送，id={result.get('id')}")


async def google_calendar_list(user_id: int, args: dict) -> MCPCallResponse:
    try:
        token, _ = await _token(user_id, args)
        from plugins.oauth.backend import google

        rows = await google.calendar_list(
            token,
            time_min=str(args.get("time_min") or "").strip() or None,
            time_max=str(args.get("time_max") or "").strip() or None,
            limit=int(args.get("limit") or 20),
        )
    except Exception as exc:
        return _err(str(exc))
    lines = [f"日历事件（{len(rows)}）："]
    for row in rows:
        lines.append(
            f"- {row.get('start')} → {row.get('end')} · {row.get('summary')}"
            + (f" · {row.get('location')}" if row.get("location") else "")
            + f"\n  id={row.get('id')}"
        )
    return _ok("\n".join(lines))


async def google_calendar_create(user_id: int, args: dict) -> MCPCallResponse:
    summary = str(args.get("summary") or "").strip()
    start = str(args.get("start") or "").strip()
    end = str(args.get("end") or "").strip()
    if not summary or not start or not end:
        return _err("summary、start、end 必填（ISO 时间）")
    try:
        token, _ = await _token(user_id, args)
        from plugins.oauth.backend import google

        row = await google.calendar_create(
            token,
            summary=summary,
            start=start,
            end=end,
            description=str(args.get("description") or "").strip() or None,
            location=str(args.get("location") or "").strip() or None,
        )
    except Exception as exc:
        return _err(str(exc))
    return _ok(f"已创建日程：{summary}（id={row.get('id')}）")


async def google_drive_search(user_id: int, args: dict) -> MCPCallResponse:
    query = str(args.get("query") or "").strip()
    try:
        token, _ = await _token(user_id, args)
        from plugins.oauth.backend import google

        rows = await google.drive_search(
            token, query, int(args.get("limit") or 10)
        )
    except Exception as exc:
        return _err(str(exc))
    lines = [f"Drive 搜索结果（{len(rows)}）："]
    for row in rows:
        lines.append(
            f"- {row.get('name')} · {row.get('mimeType')} · "
            f"{row.get('modifiedTime') or ''}\n  id={row.get('id')}"
        )
    return _ok("\n".join(lines))


async def google_drive_read(user_id: int, args: dict) -> MCPCallResponse:
    file_id = str(args.get("file_id") or "").strip()
    if not file_id:
        return _err("file_id 必填")
    try:
        token, _ = await _token(user_id, args)
        from plugins.oauth.backend import google

        data = await google.drive_read(token, file_id)
    except Exception as exc:
        return _err(str(exc))
    header = (
        f"文件：{data.get('name')}\n"
        f"类型：{data.get('mimeType')}\n"
        f"大小：{data.get('size') or '-'}\n"
    )
    if data.get("binary"):
        return _ok(header + "\n这是二进制文件，未返回内容。")
    return _ok(header + "\n" + str(data.get("content") or ""))


async def google_drive_upload(user_id: int, args: dict) -> MCPCallResponse:
    name = str(args.get("name") or "").strip()
    if not name:
        return _err("name 必填")
    content = args.get("content")
    workspace_path = str(args.get("workspace_path") or "").strip()
    if not isinstance(content, str) and not workspace_path:
        return _err("content 或 workspace_path 必须提供一个")
    try:
        if workspace_path:
            from core.paths import is_within, user_root

            root = user_root(user_id).resolve()
            path = (root / workspace_path.lstrip("/")).resolve()
            if not is_within(root, path):
                return _err("workspace_path 必须在用户 workspace 内")
            if not path.is_file():
                return _err(f"文件不存在：{workspace_path}")
            raw = path.read_bytes()[:20_000_000]
            name = name or path.name
            mime = str(args.get("mime_type") or "").strip()
            if not mime:
                mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        else:
            raw = str(content).encode("utf-8")
            mime = str(args.get("mime_type") or "text/plain").strip()
        token, _ = await _token(user_id, args)
        from plugins.oauth.backend import google

        row = await google.drive_upload(
            token, name=name, content=raw, mime_type=mime
        )
    except Exception as exc:
        return _err(str(exc))
    return _ok(
        f"已上传到 Drive：{row.get('name')}（id={row.get('id')}）"
        + (f"\n{row.get('webViewLink')}" if row.get("webViewLink") else "")
    )


TOOLS = [
    (
        MCPTool(
            name="google_gmail_search",
            description="在已连接的 Gmail 中搜索邮件。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Gmail 搜索语法，例如 from:boss is:unread"},
                    "limit": {"type": "integer", "description": "数量，默认 10"},
                    "account_id": {"type": "integer", "description": "可选，指定连接账号"},
                },
                "required": ["query"],
            },
        ),
        google_gmail_search,
    ),
    (
        MCPTool(
            name="google_gmail_read",
            description="读取一封 Gmail 邮件正文。",
            inputSchema={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                    "account_id": {"type": "integer"},
                },
                "required": ["message_id"],
            },
        ),
        google_gmail_read,
    ),
    (
        MCPTool(
            name="google_gmail_send",
            description="通过已连接的 Gmail 发送邮件。属于外部副作用，需要审批。",
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "cc": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "account_id": {"type": "integer"},
                },
                "required": ["to", "subject"],
            },
        ),
        google_gmail_send,
    ),
    (
        MCPTool(
            name="google_calendar_list",
            description="列出 Google Calendar 事件。",
            inputSchema={
                "type": "object",
                "properties": {
                    "time_min": {"type": "string", "description": "ISO 时间，默认现在"},
                    "time_max": {"type": "string", "description": "ISO 时间，默认 7 天后"},
                    "limit": {"type": "integer"},
                    "account_id": {"type": "integer"},
                },
            },
        ),
        google_calendar_list,
    ),
    (
        MCPTool(
            name="google_calendar_create",
            description="在 Google Calendar 创建事件（写操作）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "start": {"type": "string", "description": "ISO 时间"},
                    "end": {"type": "string", "description": "ISO 时间"},
                    "description": {"type": "string"},
                    "location": {"type": "string"},
                    "account_id": {"type": "integer"},
                },
                "required": ["summary", "start", "end"],
            },
        ),
        google_calendar_create,
    ),
    (
        MCPTool(
            name="google_drive_search",
            description="搜索 Google Drive 文件。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "文件名或 Drive 查询"},
                    "limit": {"type": "integer"},
                    "account_id": {"type": "integer"},
                },
            },
        ),
        google_drive_search,
    ),
    (
        MCPTool(
            name="google_drive_read",
            description="读取 Google Drive 文件；Google Docs 会导出为文本。",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_id": {"type": "string"},
                    "account_id": {"type": "integer"},
                },
                "required": ["file_id"],
            },
        ),
        google_drive_read,
    ),
    (
        MCPTool(
            name="google_drive_upload",
            description="上传文本或 workspace 文件到 Google Drive（写操作）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "content": {"type": "string"},
                    "workspace_path": {"type": "string"},
                    "mime_type": {"type": "string"},
                    "account_id": {"type": "integer"},
                },
                "required": ["name"],
            },
        ),
        google_drive_upload,
    ),
]
