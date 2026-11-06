"""Agent tools for generic business objects and threaded comments."""

from __future__ import annotations

import json

from core.ai.mcp.core import MCPCallResponse, MCPContent, MCPTool


def _ok(value) -> MCPCallResponse:
    return MCPCallResponse(content=[MCPContent(text=json.dumps(
        {"ok": True, "data": value}, ensure_ascii=False
    ))])


def _err(message: str) -> MCPCallResponse:
    return MCPCallResponse(
        content=[MCPContent(text=json.dumps({"ok": False, "error": message}, ensure_ascii=False))],
        isError=True,
    )


async def search_business_objects(user_id: int, args: dict) -> MCPCallResponse:
    from core.objects.registry import search_objects

    items = await search_objects(
        user_id,
        str(args.get("query") or ""),
        args.get("types"),
        int(args.get("limit") or 20),
    )
    return _ok({"items": items})


async def get_business_object(user_id: int, args: dict) -> MCPCallResponse:
    from core.objects.registry import resolve_object
    from core.objects.service import comment_out, list_comments

    object_type = str(args.get("type") or "").strip()
    try:
        object_id = int(args.get("id"))
    except (TypeError, ValueError):
        return _err("type 和 id 必填")
    item = await resolve_object(user_id, object_type, object_id)
    if item is None:
        return _err("对象不存在或无权限")
    rows = await list_comments(user_id, object_type, object_id, limit=100)
    return _ok({
        "object": item,
        "comments": [comment_out(row) for row in rows],
    })


async def list_business_comments(user_id: int, args: dict) -> MCPCallResponse:
    from core.objects.service import comment_out, list_comments

    object_type = str(args.get("type") or "").strip()
    try:
        object_id = int(args.get("id"))
    except (TypeError, ValueError):
        return _err("type 和 id 必填")
    include_deleted = bool(args.get("include_deleted"))
    rows = await list_comments(
        user_id, object_type, object_id,
        include_deleted=include_deleted,
        limit=int(args.get("limit") or 300),
    )
    return _ok({"items": [comment_out(row) for row in rows]})


async def comment_business_object(user_id: int, args: dict) -> MCPCallResponse:
    from core.bots.context import get_current_session_id
    from core.objects.service import ObjectCommentError, create_comment

    object_type = str(args.get("type") or "").strip()
    try:
        object_id = int(args.get("id"))
    except (TypeError, ValueError):
        return _err("type 和 id 必填")
    content = str(args.get("content") or "").strip()
    if not content:
        return _err("content 必填")
    parent_id = args.get("parent_id")
    try:
        parent_id = int(parent_id) if parent_id else None
    except (TypeError, ValueError):
        parent_id = None
    try:
        row = await create_comment(
            user_id, object_type, object_id,
            content=content,
            kind=str(args.get("kind") or "material"),
            title=args.get("title") or None,
            author="assistant",
            parent_id=parent_id,
            session_id=get_current_session_id(),
            metadata=args.get("metadata") if isinstance(args.get("metadata"), dict) else None,
        )
    except ObjectCommentError as e:
        return _err(str(e))
    return _ok({
        "comment": row,
        "message": f"已保存到对象 {object_type}:{object_id}",
    })


async def update_business_comment(user_id: int, args: dict) -> MCPCallResponse:
    from core.objects.service import ObjectCommentError, update_comment

    try:
        comment_id = int(args.get("comment_id"))
    except (TypeError, ValueError):
        return _err("comment_id 必填")
    if args.get("content") is None and args.get("title") is None:
        return _err("content 或 title 至少提供一个")
    try:
        row = await update_comment(
            user_id, comment_id,
            content=args.get("content"),
            title=args.get("title"),
        )
    except ObjectCommentError as e:
        return _err(str(e))
    if row is None:
        return _err("评论不存在")
    return _ok(row)


async def delete_business_comment(user_id: int, args: dict) -> MCPCallResponse:
    from core.objects.service import delete_comment

    try:
        comment_id = int(args.get("comment_id"))
    except (TypeError, ValueError):
        return _err("comment_id 必填")
    if not args.get("confirmed"):
        return MCPCallResponse(content=[MCPContent(text=json.dumps({
            "confirmation_required": True,
            "message": "删除评论需要用户确认；确认后以 confirmed=true 重新调用。",
            "comment_id": comment_id,
        }, ensure_ascii=False))])
    ok = await delete_comment(user_id, comment_id)
    if not ok:
        return _err("评论不存在")
    return _ok({"comment_id": comment_id, "deleted": True})


TOOLS = [
    (
        MCPTool(
            name="search_business_objects",
            description=(
                "跨日程、邮件、资讯、笔记、待办、文件和项目搜索业务对象。"
                "返回统一结构（type/id/title/subtitle/url），用于在用户指代不清时让用户确认。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "关键词；留空返回最近对象"},
                    "types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选：schedule_event/mail_message/rss_entry/note/todo/file/project",
                    },
                    "limit": {"type": "integer", "description": "最多返回数量，默认 20"},
                },
            },
        ),
        search_business_objects,
    ),
    (
        MCPTool(
            name="get_business_object",
            description="读取一个业务对象的详情和已有评论/材料。",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string", "description": "对象类型"},
                    "id": {"type": "integer", "description": "对象 ID"},
                },
                "required": ["type", "id"],
            },
        ),
        get_business_object,
    ),
    (
        MCPTool(
            name="list_business_comments",
            description="读取某个业务对象的评论、备注和材料（平铺返回 parent_id，可自行组树）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string", "description": "对象类型"},
                    "id": {"type": "integer", "description": "对象 ID"},
                    "include_deleted": {"type": "boolean", "description": "是否包含已删除评论"},
                    "limit": {"type": "integer", "description": "最多返回数量，默认 300"},
                },
                "required": ["type", "id"],
            },
        ),
        list_business_comments,
    ),
    (
        MCPTool(
            name="comment_business_object",
            description=(
                "给业务对象添加评论、备注或材料。用户要求生成与某个对象相关的内容时，"
                "必须用这个工具保存到对象下，而不是只在聊天里回复。回复评论时传 parent_id。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string", "description": "对象类型"},
                    "id": {"type": "integer", "description": "对象 ID"},
                    "kind": {
                        "type": "string",
                        "enum": ["comment", "note", "material", "ai_summary"],
                        "description": "材料通常用 material，普通备注用 note/comment",
                    },
                    "title": {"type": "string", "description": "材料标题，可选"},
                    "content": {"type": "string", "description": "Markdown 或纯文本内容"},
                    "parent_id": {"type": "integer", "description": "回复某条评论时传入"},
                    "metadata": {"type": "object", "description": "可选附加信息"},
                },
                "required": ["type", "id", "content"],
            },
        ),
        comment_business_object,
    ),
    (
        MCPTool(
            name="update_business_comment",
            description="修改自己对象下的评论或材料内容。",
            inputSchema={
                "type": "object",
                "properties": {
                    "comment_id": {"type": "integer"},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["comment_id"],
            },
        ),
        update_business_comment,
    ),
    (
        MCPTool(
            name="delete_business_comment",
            description="删除业务对象下的评论（软删除）。需要用户确认。",
            inputSchema={
                "type": "object",
                "properties": {
                    "comment_id": {"type": "integer"},
                    "confirmed": {"type": "boolean"},
                },
                "required": ["comment_id"],
            },
        ),
        delete_business_comment,
    ),
]
