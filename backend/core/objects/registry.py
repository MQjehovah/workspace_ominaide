"""Resolve business objects into one normalized shape for UI and the agent."""

from __future__ import annotations

from core.logging import get_logger
log = get_logger(__name__)

from datetime import datetime
from typing import Any

from sqlalchemy import desc, or_, select

from core.database.session import async_session

OBJECT_TYPES = {
    "schedule_event": "日程",
    "mail_message": "邮件",
    "source_item": "资讯",
    "note": "笔记",
    "todo": "待办",
    "file": "文件",
    "project": "项目",
}

SOURCE_LABELS = {
    "dingtalk": "钉钉",
    "agent": "助手",
    "manual": "手动",
    "system": "系统",
}


def _fmt(value: datetime | None) -> str | None:
    return value.strftime("%Y-%m-%d %H:%M") if value else None


def _clip(value: Any, size: int = 500) -> str:
    text = str(value or "").replace("\x00", " ").strip()
    return text[:size]


def _source_label(value: str | None) -> str:
    return SOURCE_LABELS.get(str(value or "manual"), str(value or "手动"))


async def _resolve_schedule(user_id: int, object_id: int) -> dict | None:
    from plugins.schedule.backend.models import Event

    async with async_session() as db:
        row = (await db.execute(
            select(Event).where(Event.id == object_id, Event.user_id == user_id)
        )).scalar_one_or_none()
    if row is None:
        return None
    source = getattr(row, "source", None) or "manual"
    start = _fmt(row.start_time)
    end = _fmt(row.end_time)
    return {
        "type": "schedule_event",
        "id": row.id,
        "title": row.title,
        "subtitle": " · ".join(part for part in (start, end, _source_label(source)) if part),
        "time": start,
        "source": source,
        "source_label": _source_label(source),
        "preview": _clip(getattr(row, "notes", "") or "", 300),
        "url": f"/schedule?event={row.id}",
        "status": getattr(row, "status", None) or "confirmed",
        "metadata": getattr(row, "external_meta", None) or {},
    }


async def _resolve_mail(user_id: int, object_id: int) -> dict | None:
    from plugins.mail.backend.models import MailMessage

    async with async_session() as db:
        row = (await db.execute(
            select(MailMessage).where(MailMessage.id == object_id, MailMessage.user_id == user_id)
        )).scalar_one_or_none()
    if row is None:
        return None
    when = _fmt(row.date or row.created_at)
    return {
        "type": "mail_message",
        "id": row.id,
        "title": row.subject or "(无主题)",
        "subtitle": " · ".join(part for part in (row.from_address, when) if part),
        "time": when,
        "source": "mail",
        "source_label": "邮件",
        "preview": _clip(row.preview or row.content or "", 300),
        "url": f"/mail?message={row.id}",
        "status": "unread" if not row.read else "read",
        "metadata": {"from": row.from_address, "important": bool(row.important)},
    }


async def _resolve_source_item(user_id: int, object_id: int) -> dict | None:
    from plugins.sources.backend.models import ContentItem, ContentSource

    async with async_session() as db:
        row = (await db.execute(
            select(ContentItem)
            .join(ContentSource, ContentSource.id == ContentItem.source_id)
            .where(ContentItem.id == object_id, ContentSource.user_id == user_id)
        )).scalar_one_or_none()
        source = None
        if row is not None:
            source = (await db.execute(
                select(ContentSource).where(ContentSource.id == row.source_id)
            )).scalar_one_or_none()
    if row is None:
        return None
    when = _fmt(row.published or row.created_at)
    return {
        "type": "source_item",
        "id": row.id,
        "title": row.title,
        "subtitle": " · ".join(
            part for part in ((source.title if source else None), when) if part
        ),
        "time": when,
        "source": "sources",
        "source_label": "资讯",
        "preview": _clip(row.summary or row.content or "", 300),
        "url": f"/sources?item={row.id}",
        "status": "unread" if not row.read else "read",
        "metadata": {"link": row.link, "author": row.author},
    }


async def _resolve_note(user_id: int, object_id: int) -> dict | None:
    from plugins.notes.backend.models import PluginNote

    async with async_session() as db:
        row = (await db.execute(
            select(PluginNote).where(PluginNote.id == object_id, PluginNote.user_id == user_id)
        )).scalar_one_or_none()
    if row is None:
        return None
    when = _fmt(row.updated_at or row.created_at)
    return {
        "type": "note",
        "id": row.id,
        "title": row.title or "(无标题)",
        "subtitle": when or "",
        "time": when,
        "source": "note",
        "source_label": "笔记",
        "preview": _clip(row.content or "", 300),
        "url": f"/notes?id={row.id}",
        "status": "folder" if row.is_folder else "active",
        "metadata": {"parent_id": row.parent_id},
    }


async def _resolve_todo(user_id: int, object_id: int) -> dict | None:
    from plugins.todo.backend.models import PluginTodoItem

    async with async_session() as db:
        row = (await db.execute(
            select(PluginTodoItem).where(
                PluginTodoItem.id == object_id, PluginTodoItem.user_id == user_id
            )
        )).scalar_one_or_none()
    if row is None:
        return None
    when = _fmt(row.due_date)
    return {
        "type": "todo",
        "id": row.id,
        "title": row.title,
        "subtitle": " · ".join(part for part in (row.status, when and f"截止 {when}") if part),
        "time": when,
        "source": "todo",
        "source_label": "待办",
        "preview": _clip(row.description or "", 300),
        "url": f"/apps/todo?item={row.id}",
        "status": row.status,
        "metadata": {"priority": row.priority, "tags": row.tags or []},
    }


async def _resolve_file(user_id: int, object_id: int) -> dict | None:
    from plugins.files.backend.models import File

    async with async_session() as db:
        row = (await db.execute(
            select(File).where(
                File.id == object_id, File.user_id == user_id, File.status != "trash"
            )
        )).scalar_one_or_none()
    if row is None:
        return None
    when = _fmt(row.updated_at or row.created_at)
    size_kb = max(1, round((row.size or 0) / 1024))
    return {
        "type": "file",
        "id": row.id,
        "title": row.original_name,
        "subtitle": " · ".join(part for part in (row.mime_type, f"{size_kb} KB", when) if part),
        "time": when,
        "source": "file",
        "source_label": "文件",
        "preview": row.folder_path or "/",
        "url": f"/files?file={row.id}",
        "status": row.status,
        "metadata": {"size": row.size, "mime": row.mime_type, "folder": row.folder_path},
    }


async def _resolve_project(user_id: int, object_id: int) -> dict | None:
    from plugins.projects.backend.models import Project

    async with async_session() as db:
        row = (await db.execute(
            select(Project).where(Project.id == object_id, Project.user_id == user_id)
        )).scalar_one_or_none()
    if row is None:
        return None
    when = _fmt(row.updated_at or row.created_at)
    return {
        "type": "project",
        "id": row.id,
        "title": row.name,
        "subtitle": " · ".join(part for part in (row.path, row.status, when) if part),
        "time": when,
        "source": "project",
        "source_label": "项目",
        "preview": _clip(row.description or "", 300),
        "url": f"/projects?project={row.id}",
        "status": row.status,
        "metadata": {"path": row.path, "repo_url": row.repo_url},
    }


_RESOLVERS = {
    "schedule_event": _resolve_schedule,
    "mail_message": _resolve_mail,
    "source_item": _resolve_source_item,
    "note": _resolve_note,
    "todo": _resolve_todo,
    "file": _resolve_file,
    "project": _resolve_project,
}


def normalise_types(types: Any) -> list[str]:
    if isinstance(types, str):
        items = [item.strip() for item in types.split(",")]
    elif isinstance(types, list):
        items = [str(item).strip() for item in types]
    else:
        items = list(OBJECT_TYPES)
    return [item for item in items if item in OBJECT_TYPES]


async def resolve_object(user_id: int, object_type: str, object_id: int) -> dict | None:
    resolver = _RESOLVERS.get(str(object_type))
    if resolver is None:
        return None
    return await resolver(user_id, int(object_id))


async def _search_schedule(user_id: int, query: str, limit: int) -> list[int]:
    from plugins.schedule.backend.models import Event

    async with async_session() as db:
        q = select(Event.id).where(Event.user_id == user_id)
        if query:
            like = f"%{query}%"
            q = q.where(or_(Event.title.ilike(like), Event.notes.ilike(like)))
        q = q.order_by(desc(Event.start_time)).limit(limit)
        return list((await db.execute(q)).scalars().all())


async def _search_mail(user_id: int, query: str, limit: int) -> list[int]:
    from plugins.mail.backend.models import MailMessage

    async with async_session() as db:
        q = select(MailMessage.id).where(MailMessage.user_id == user_id)
        if query:
            like = f"%{query}%"
            q = q.where(or_(
                MailMessage.subject.ilike(like),
                MailMessage.from_address.ilike(like),
                MailMessage.preview.ilike(like),
            ))
        q = q.order_by(desc(MailMessage.date), desc(MailMessage.id)).limit(limit)
        return list((await db.execute(q)).scalars().all())


async def _search_source_items(user_id: int, query: str, limit: int) -> list[int]:
    from plugins.sources.backend.models import ContentItem, ContentSource

    async with async_session() as db:
        q = select(ContentItem.id).join(
            ContentSource, ContentSource.id == ContentItem.source_id
        ).where(ContentSource.user_id == user_id)
        if query:
            like = f"%{query}%"
            q = q.where(or_(
                ContentItem.title.ilike(like),
                ContentItem.summary.ilike(like),
                ContentItem.content.ilike(like),
            ))
        q = q.order_by(desc(ContentItem.published), desc(ContentItem.id)).limit(limit)
        return list((await db.execute(q)).scalars().all())


async def _search_note(user_id: int, query: str, limit: int) -> list[int]:
    from plugins.notes.backend.models import PluginNote

    async with async_session() as db:
        q = select(PluginNote.id).where(PluginNote.user_id == user_id)
        if query:
            like = f"%{query}%"
            q = q.where(or_(PluginNote.title.ilike(like), PluginNote.content.ilike(like)))
        q = q.order_by(desc(PluginNote.updated_at), desc(PluginNote.id)).limit(limit)
        return list((await db.execute(q)).scalars().all())


async def _search_todo(user_id: int, query: str, limit: int) -> list[int]:
    from plugins.todo.backend.models import PluginTodoItem

    async with async_session() as db:
        q = select(PluginTodoItem.id).where(PluginTodoItem.user_id == user_id)
        if query:
            like = f"%{query}%"
            q = q.where(or_(PluginTodoItem.title.ilike(like), PluginTodoItem.description.ilike(like)))
        q = q.order_by(desc(PluginTodoItem.updated_at), desc(PluginTodoItem.id)).limit(limit)
        return list((await db.execute(q)).scalars().all())


async def _search_file(user_id: int, query: str, limit: int) -> list[int]:
    from plugins.files.backend.models import File

    async with async_session() as db:
        q = select(File.id).where(File.user_id == user_id, File.status != "trash")
        if query:
            like = f"%{query}%"
            q = q.where(or_(File.original_name.ilike(like), File.folder_path.ilike(like)))
        q = q.order_by(desc(File.updated_at), desc(File.id)).limit(limit)
        return list((await db.execute(q)).scalars().all())


async def _search_project(user_id: int, query: str, limit: int) -> list[int]:
    from plugins.projects.backend.models import Project

    async with async_session() as db:
        q = select(Project.id).where(Project.user_id == user_id)
        if query:
            like = f"%{query}%"
            q = q.where(or_(
                Project.name.ilike(like),
                Project.path.ilike(like),
                Project.description.ilike(like),
            ))
        q = q.order_by(desc(Project.updated_at), desc(Project.id)).limit(limit)
        return list((await db.execute(q)).scalars().all())


_SEARCHERS = {
    "schedule_event": _search_schedule,
    "mail_message": _search_mail,
    "source_item": _search_source_items,
    "note": _search_note,
    "todo": _search_todo,
    "file": _search_file,
    "project": _search_project,
}


async def search_objects(
    user_id: int,
    query: str = "",
    types: Any = None,
    limit: int = 20,
) -> list[dict]:
    query = (query or "").strip()
    selected = normalise_types(types)
    limit = max(1, min(int(limit or 20), 50))
    per_type = max(3, min(10, limit))
    results: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for object_type in selected:
        searcher = _SEARCHERS[object_type]
        try:
            ids = await searcher(user_id, query, per_type)
        except Exception as e:
            log.warning(f"[objects] search {object_type} failed: {e}")
            continue
        for object_id in ids:
            item = await resolve_object(user_id, object_type, object_id)
            if item is not None and (object_type, object_id) not in seen:
                seen.add((object_type, object_id))
                item["match"] = "object"
                results.append(item)

    # Generated materials and comments are first-class searchable content too.
    if query:
        from core.objects.models import BusinessComment

        async with async_session() as db:
            rows = list((await db.execute(
                select(BusinessComment).where(
                    BusinessComment.user_id == user_id,
                    BusinessComment.deleted_at.is_(None),
                    BusinessComment.content.ilike(f"%{query}%"),
                ).order_by(desc(BusinessComment.created_at)).limit(limit)
            )).scalars().all())
        for row in rows:
            key = (row.object_type, row.object_id)
            if key in seen:
                continue
            item = await resolve_object(user_id, row.object_type, row.object_id)
            if item is None:
                continue
            seen.add(key)
            item["match"] = "comment"
            item["snippet"] = _clip(row.content, 200)
            item["comment_id"] = row.id
            results.append(item)

    results.sort(key=lambda item: str(item.get("time") or ""), reverse=True)
    return results[:limit]


async def build_context_block(
    user_id: int,
    refs: list[dict] | None,
    focus_comment_id: int | None = None,
) -> str | None:
    if not refs:
        return None
    lines = ["用户当前引用了以下业务对象，回答和生成内容必须围绕它们："]
    seen: set[tuple[str, int]] = set()
    for ref in refs[:8]:
        object_type = str(ref.get("type") or "")
        try:
            object_id = int(ref.get("id"))
        except (TypeError, ValueError):
            continue
        key = (object_type, object_id)
        if key in seen:
            continue
        seen.add(key)
        item = await resolve_object(user_id, object_type, object_id)
        if item is None:
            lines.append(f"- [{OBJECT_TYPES.get(object_type, object_type)} #{object_id}] 未找到或无权限")
            continue
        lines.append(
            f"- [{item['source_label']} #{item['id']}] {item['title']} | {item['subtitle']}"
            f" | 链接 {item['url']}"
        )
        if item.get("preview"):
            lines.append(f"  摘要：{_clip(item['preview'], 500)}")

    if focus_comment_id:
        from core.objects.models import BusinessComment

        async with async_session() as db:
            comment = (await db.execute(
                select(BusinessComment).where(
                    BusinessComment.id == int(focus_comment_id),
                    BusinessComment.user_id == user_id,
                )
            )).scalar_one_or_none()
        if comment is not None:
            lines.append(
                f"\n用户正在查看评论 #{comment.id}（作者 {comment.author}，类型 {comment.kind}）："
                f"\n{_clip(comment.content, 2000)}"
            )
            if comment.parent_id:
                lines.append(f"回复时请使用 parent_id={comment.id}。")

    lines.extend([
        "",
        "规则：",
        "- 用户说“这个/这条/刚才那个”时，优先指上面引用的对象。",
        "- 需要保存的备注、评论或材料，必须调用 comment_business_object 写入对应对象，不能只留在聊天里。",
        "- 日程的时间/标题修改使用 update_schedule_event，取消使用 cancel_schedule_event。",
        "- 指代不明确时先调用 search_business_objects 并让用户确认，不要猜。",
    ])
    return "\n".join(lines)
