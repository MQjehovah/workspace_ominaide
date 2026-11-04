"""CRUD and management tools for the assistant.

These complement the existing create/read tools with update/delete/manage
operations. Handlers import plugin services lazily so startup order stays
simple and plugins can be loaded independently.
"""
import asyncio
import smtplib
from email.message import EmailMessage

from sqlalchemy import select

from core.ai.mcp.core import MCPCallResponse, MCPContent, MCPTool
from core.database.session import async_session


def _ok(text: str) -> MCPCallResponse:
    return MCPCallResponse(content=[MCPContent(text=text)])


def _err(text: str) -> MCPCallResponse:
    return MCPCallResponse(isError=True, content=[MCPContent(text=text)])


def _int(args: dict, key: str, required: bool = True) -> int:
    try:
        value = int(args.get(key) or 0)
    except (TypeError, ValueError):
        value = 0
    if required and value <= 0:
        raise ValueError(f"{key} 必填")
    return value


async def _bot_id(user_id: int) -> int:
    from core.bots.context import get_current_bot_id
    from core.bots.registry import get_or_create_default_bot

    bot_id = get_current_bot_id()
    if bot_id:
        return bot_id
    bot = await get_or_create_default_bot(user_id)
    return bot.id


# ---------------------------------------------------------------------------
# Todos
# ---------------------------------------------------------------------------

async def todo_update(user_id: int, args: dict) -> MCPCallResponse:
    from plugins.todo.backend.schemas import TodoUpdate
    from plugins.todo.backend.service import update_todo

    try:
        todo_id = _int(args, "todo_id")
    except ValueError as e:
        return _err(str(e))
    fields = {
        key: args[key]
        for key in ("title", "description", "status", "priority", "due_date", "tags")
        if args.get(key) is not None
    }
    if not fields:
        return _err("没有要更新的字段")
    async with async_session() as db:
        try:
            todo = await update_todo(db, user_id, todo_id, TodoUpdate(**fields))
        except ValueError as e:
            return _err(str(e))
        await db.commit()
    return _ok(f"已更新待办 #{todo.id}：{todo.title}（状态 {todo.status}）")


async def todo_complete(user_id: int, args: dict) -> MCPCallResponse:
    args = {**args, "status": "done"}
    return await todo_update(user_id, args)


async def todo_delete(user_id: int, args: dict) -> MCPCallResponse:
    from plugins.todo.backend.service import delete_todo

    try:
        todo_id = _int(args, "todo_id")
    except ValueError as e:
        return _err(str(e))
    async with async_session() as db:
        try:
            await delete_todo(db, user_id, todo_id)
        except ValueError as e:
            return _err(str(e))
        await db.commit()
    return _ok(f"已删除待办 #{todo_id}")


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

async def event_update(user_id: int, args: dict) -> MCPCallResponse:
    from plugins.schedule.backend.schemas import EventUpdate
    from plugins.schedule.backend.service import update_event

    try:
        event_id = _int(args, "event_id")
    except ValueError as e:
        return _err(str(e))
    fields = {
        key: args[key]
        for key in ("title", "start_time", "end_time", "notes", "color", "remind_before")
        if args.get(key) is not None
    }
    if not fields:
        return _err("没有要更新的字段")
    async with async_session() as db:
        ev = await update_event(db, user_id, event_id, EventUpdate(**fields))
        if ev is None:
            return _err(f"日程 #{event_id} 不存在")
        await db.commit()
    return _ok(f"已更新日程 #{ev.id}：{ev.title} {ev.start_time:%Y-%m-%d %H:%M}")


async def event_delete(user_id: int, args: dict) -> MCPCallResponse:
    from plugins.schedule.backend.service import delete_event

    try:
        event_id = _int(args, "event_id")
    except ValueError as e:
        return _err(str(e))
    async with async_session() as db:
        ok = await delete_event(db, user_id, event_id)
        await db.commit()
    if not ok:
        return _err(f"日程 #{event_id} 不存在")
    return _ok(f"已删除日程 #{event_id}")


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

async def note_update(user_id: int, args: dict) -> MCPCallResponse:
    from plugins.notes.backend.schemas import NoteUpdate
    from plugins.notes.backend.service import update_note

    try:
        note_id = _int(args, "note_id")
    except ValueError as e:
        return _err(str(e))
    fields = {
        key: args[key]
        for key in ("title", "content", "parent_id", "is_folder", "icon", "sort_order")
        if args.get(key) is not None
    }
    if not fields:
        return _err("没有要更新的字段")
    async with async_session() as db:
        note = await update_note(db, user_id, note_id, NoteUpdate(**fields))
        if note is None:
            return _err(f"笔记 #{note_id} 不存在")
        await db.commit()
    return _ok(f"已更新笔记 #{note.id}：{note.title}")


async def note_delete(user_id: int, args: dict) -> MCPCallResponse:
    from plugins.notes.backend.service import delete_note

    try:
        note_id = _int(args, "note_id")
    except ValueError as e:
        return _err(str(e))
    async with async_session() as db:
        await delete_note(db, user_id, note_id)
        await db.commit()
    return _ok(f"已删除笔记 #{note_id}")


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

async def notification_mark_read(user_id: int, args: dict) -> MCPCallResponse:
    from plugins.notifications.backend import service

    try:
        notification_id = _int(args, "notification_id")
    except ValueError as e:
        return _err(str(e))
    async with async_session() as db:
        ok = await service.mark_read(db, user_id, notification_id)
        await db.commit()
    if not ok:
        return _err(f"通知 #{notification_id} 不存在")
    return _ok(f"通知 #{notification_id} 已标记为已读")


async def notification_mark_all_read(user_id: int, args: dict) -> MCPCallResponse:
    from plugins.notifications.backend import service

    async with async_session() as db:
        await service.mark_all_read(db, user_id)
        await db.commit()
    return _ok("所有通知已标记为已读")


async def notification_send(user_id: int, args: dict) -> MCPCallResponse:
    from plugins.notifications.backend import service
    from core.wschannel.hub import host_channel

    title = (args.get("title") or "").strip()
    body = (args.get("body") or "").strip() or None
    link = (args.get("link") or "").strip() or None
    if not title:
        return _err("title 必填")
    async with async_session() as db:
        n = await service.create_notification(db, user_id, title, body, "info", link)
        await db.commit()
        nid = n.id
    try:
        await host_channel.broadcast(
            user_id,
            "notifications",
            {"type": "new_notification", "id": nid, "title": title, "body": body or ""},
        )
    except Exception:
        pass
    return _ok(f"已发送通知 #{nid}：{title}")


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

async def memory_list(user_id: int, args: dict) -> MCPCallResponse:
    from core.bots.memory import list_memories

    bot_id = await _bot_id(user_id)
    try:
        limit = min(max(int(args.get("limit") or 50), 1), 200)
    except (TypeError, ValueError):
        limit = 50
    memories = await list_memories(user_id, bot_id, limit, args.get("kind") or None)
    if not memories:
        return _ok("当前 Bot 还没有长期记忆。")
    lines = ["当前 Bot 的记忆："]
    for mem in memories:
        lines.append(f"- #{mem.id} [{mem.kind}] {mem.content[:300]}")
    return _ok("\n".join(lines))


async def memory_delete(user_id: int, args: dict) -> MCPCallResponse:
    from core.bots.memory import delete_memory

    try:
        memory_id = _int(args, "memory_id")
    except ValueError as e:
        return _err(str(e))
    bot_id = await _bot_id(user_id)
    ok = await delete_memory(user_id, bot_id, memory_id)
    if not ok:
        return _err(f"记忆 #{memory_id} 不存在")
    return _ok(f"已删除记忆 #{memory_id}")


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

async def file_delete(user_id: int, args: dict) -> MCPCallResponse:
    from plugins.files.backend import service

    try:
        file_id = _int(args, "file_id")
    except ValueError as e:
        return _err(str(e))
    permanent = bool(args.get("permanent"))
    async with async_session() as db:
        try:
            if permanent:
                await service.permanent_delete(db, user_id, file_id)
            else:
                await service.trash_file(db, user_id, file_id)
        except ValueError as e:
            return _err(str(e))
        await db.commit()
    return _ok(f"已{'永久删除' if permanent else '移入回收站'}文件 #{file_id}")


async def file_rename(user_id: int, args: dict) -> MCPCallResponse:
    from plugins.files.backend import service

    try:
        file_id = _int(args, "file_id")
    except ValueError as e:
        return _err(str(e))
    new_name = (args.get("new_name") or "").strip()
    if not new_name:
        return _err("new_name 必填")
    async with async_session() as db:
        try:
            f = await service.rename_file(db, user_id, file_id, new_name)
        except ValueError as e:
            return _err(str(e))
        await db.commit()
    return _ok(f"已重命名 #{f.id} 为 {f.original_name}")


async def file_move(user_id: int, args: dict) -> MCPCallResponse:
    from plugins.files.backend import service

    try:
        file_id = _int(args, "file_id")
    except ValueError as e:
        return _err(str(e))
    folder = (args.get("folder_path") or "/").strip() or "/"
    async with async_session() as db:
        try:
            f = await service.move_file(db, user_id, file_id, folder)
        except ValueError as e:
            return _err(str(e))
        await db.commit()
    return _ok(f"已移动 #{f.id} 到 {f.folder_path}")


async def file_create_folder(user_id: int, args: dict) -> MCPCallResponse:
    from plugins.files.backend import service
    from plugins.files.backend.schemas import CreateFolderRequest

    name = (args.get("name") or "").strip()
    if not name:
        return _err("name 必填")
    parent = (args.get("parent_path") or "/").strip() or "/"
    async with async_session() as db:
        folder = await service.create_folder(db, user_id, CreateFolderRequest(name=name, parent_path=parent))
        await db.commit()
    return _ok(f"已创建文件夹 #{folder.id}：{folder.original_name}")


async def read_file_content(user_id: int, args: dict) -> MCPCallResponse:
    from core.minio.client import minio_client
    from plugins.files.backend import service
    from plugins.notes.backend.importers import ImportFailed, extract_document

    try:
        file_id = _int(args, "file_id")
    except ValueError as e:
        return _err(str(e))
    if minio_client is None:
        return _err("MinIO 未配置，无法读取文件")
    async with async_session() as db:
        record = await service.get_file(db, user_id, file_id)
    if record is None:
        return _err(f"文件 #{file_id} 不存在")
    if record.is_folder:
        return _err("这是文件夹，不能读取正文")
    try:
        obj = await asyncio.to_thread(minio_client.get_object, record.bucket, record.object_key)
        data = await asyncio.to_thread(obj.read)
        obj.close()
        obj.release_conn()
        title, text = await asyncio.to_thread(extract_document, record.original_name, data)
    except ImportFailed as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"读取文件失败：{str(e)[:160]}")
    try:
        limit = min(max(int(args.get("max_chars") or 15000), 500), 50000)
    except (TypeError, ValueError):
        limit = 15000
    truncated = len(text) > limit
    return _ok(
        f"文件：{record.original_name}\n标题：{title}\n\n{text[:limit]}"
        + ("\n\n…（已截断）" if truncated else "")
    )


# ---------------------------------------------------------------------------
# Mail
# ---------------------------------------------------------------------------

async def mail_read(user_id: int, args: dict) -> MCPCallResponse:
    from plugins.mail.backend.models import MailEvent

    try:
        event_id = _int(args, "mail_id")
    except ValueError as e:
        return _err(str(e))
    async with async_session() as db:
        event = (
            await db.execute(
                select(MailEvent).where(
                    MailEvent.id == event_id, MailEvent.user_id == user_id
                )
            )
        ).scalar_one_or_none()
    if event is None:
        return _err(f"邮件 #{event_id} 不存在")
    return _ok(
        "\n".join(
            [
                f"主题：{event.subject or '(无主题)'}",
                f"发件人：{event.from_address or '-'}",
                f"时间：{event.date or '-'}",
                "",
                (event.content or event.preview or "(无正文)")[:15000],
            ]
        )
    )


def _send_mail_sync(account, to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = account.email
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if account.smtp_tls and account.smtp_port == 465:
        server = smtplib.SMTP_SSL(account.smtp_host, account.smtp_port, timeout=20)
    else:
        server = smtplib.SMTP(account.smtp_host, account.smtp_port, timeout=20)
        if account.smtp_tls:
            server.starttls()
    try:
        server.login(account.username, account.password)
        server.send_message(msg)
    finally:
        server.quit()


async def mail_send(user_id: int, args: dict) -> MCPCallResponse:
    from plugins.mail.backend import service

    to = (args.get("to") or "").strip()
    subject = (args.get("subject") or "").strip()
    body = (args.get("body") or "").strip()
    if not to or not subject:
        return _err("to 和 subject 必填")
    async with async_session() as db:
        accounts = await service.list_accounts(db, user_id)
    if not accounts:
        return _err("还没有配置邮件账户")
    account = None
    if args.get("account_id"):
        account = next((a for a in accounts if a.id == int(args["account_id"])), None)
    account = account or accounts[0]
    try:
        await asyncio.to_thread(_send_mail_sync, account, to, subject, body)
    except Exception as e:
        return _err(f"发送失败：{str(e)[:200]}")
    return _ok(f"邮件已发送到 {to}")


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

async def project_create(user_id: int, args: dict) -> MCPCallResponse:
    from plugins.projects.backend import service
    from plugins.projects.backend.schemas import ProjectCreate

    name = (args.get("name") or "").strip()
    if not name:
        return _err("name 必填")
    try:
        project = await service.create_project(
            user_id,
            ProjectCreate(
                name=name,
                path=(args.get("path") or "").strip(),
                is_git=bool(args.get("is_git", True)),
                repo_url=(args.get("repo_url") or "").strip() or None,
                default_branch=(args.get("default_branch") or "master").strip() or "master",
                description=args.get("description"),
            ),
        )
    except ValueError as e:
        return _err(str(e))
    return _ok(f"已添加项目 #{project.id}：{project.name} -> {project.path}")


async def project_update(user_id: int, args: dict) -> MCPCallResponse:
    from plugins.projects.backend import service
    from plugins.projects.backend.schemas import ProjectUpdate

    try:
        project_id = _int(args, "project_id")
    except ValueError as e:
        return _err(str(e))
    fields = {
        key: args[key]
        for key in ("name", "path", "is_git", "repo_url", "default_branch", "description")
        if args.get(key) is not None
    }
    if not fields:
        return _err("没有要更新的字段")
    try:
        project = await service.update_project(user_id, project_id, ProjectUpdate(**fields))
    except ValueError as e:
        return _err(str(e))
    if project is None:
        return _err(f"项目 #{project_id} 不存在")
    return _ok(f"已更新项目 #{project.id}：{project.name}")


async def project_delete(user_id: int, args: dict) -> MCPCallResponse:
    from plugins.projects.backend import service

    try:
        project_id = _int(args, "project_id")
    except ValueError as e:
        return _err(str(e))
    try:
        ok = await service.delete_project(user_id, project_id)
    except ValueError as e:
        return _err(str(e))
    if not ok:
        return _err(f"项目 #{project_id} 不存在")
    return _ok(f"已删除项目 #{project_id}（包含项目目录）")


# ---------------------------------------------------------------------------
# Routines
# ---------------------------------------------------------------------------

async def routine_list(user_id: int, args: dict) -> MCPCallResponse:
    from core.bots.routines import list_routines

    bot_id = await _bot_id(user_id)
    routines = await list_routines(user_id, bot_id)
    if not routines:
        return _ok("当前 Bot 还没有例程。")
    lines = ["当前 Bot 的例程："]
    for r in routines:
        when = r.cron_expr or r.event_type or "manual"
        lines.append(
            f"- #{r.id} {r.name} · {r.trigger_type}/{when} · "
            f"{'启用' if r.enabled else '停用'} · 下次 {r.next_run_at or '-'}"
        )
    return _ok("\n".join(lines))


async def routine_create(user_id: int, args: dict) -> MCPCallResponse:
    from core.bots.routines import create_routine

    name = (args.get("name") or "").strip()
    if not name:
        return _err("name 必填")
    bot_id = await _bot_id(user_id)
    try:
        routine = await create_routine(
            user_id,
            bot_id,
            name,
            trigger_type=(args.get("trigger_type") or "cron"),
            cron_expr=args.get("cron_expr"),
            event_type=args.get("event_type"),
            event_filter=args.get("event_filter"),
            prompt=args.get("prompt"),
            enabled=bool(args.get("enabled", True)),
        )
    except ValueError as e:
        return _err(str(e))
    return _ok(f"已创建例程 #{routine.id}：{routine.name}")


async def routine_update(user_id: int, args: dict) -> MCPCallResponse:
    from core.bots.routines import update_routine

    try:
        routine_id = _int(args, "routine_id")
    except ValueError as e:
        return _err(str(e))
    fields = {
        key: args[key]
        for key in ("name", "trigger_type", "cron_expr", "event_type", "event_filter", "prompt", "enabled")
        if key in args
    }
    if not fields:
        return _err("没有要更新的字段")
    try:
        routine = await update_routine(user_id, routine_id, fields)
    except ValueError as e:
        return _err(str(e))
    if routine is None:
        return _err(f"例程 #{routine_id} 不存在")
    return _ok(f"已更新例程 #{routine.id}：{routine.name}")


async def routine_delete(user_id: int, args: dict) -> MCPCallResponse:
    from core.bots.routines import delete_routine

    try:
        routine_id = _int(args, "routine_id")
    except ValueError as e:
        return _err(str(e))
    ok = await delete_routine(user_id, routine_id)
    if not ok:
        return _err(f"例程 #{routine_id} 不存在")
    return _ok(f"已删除例程 #{routine_id}")


async def routine_run(user_id: int, args: dict) -> MCPCallResponse:
    from core.bots.routines import run_routine_now

    try:
        routine_id = _int(args, "routine_id")
    except ValueError as e:
        return _err(str(e))
    run = await run_routine_now(user_id, routine_id)
    if run is None:
        return _err(f"例程 #{routine_id} 不存在")
    return _ok(f"已立即执行例程 #{routine_id}，创建 Run #{run.id}")


# ---------------------------------------------------------------------------
# RSS
# ---------------------------------------------------------------------------

async def rss_list_feeds(user_id: int, args: dict) -> MCPCallResponse:
    from plugins.rss.backend import service

    async with async_session() as db:
        feeds = await service.list_feeds(db, user_id)
    if not feeds:
        return _ok("还没有 RSS 订阅。")
    lines = ["RSS 订阅："]
    for f in feeds:
        lines.append(f"- #{f.id} {f.title or f.url} · {f.url}")
    return _ok("\n".join(lines))


async def rss_add_feed(user_id: int, args: dict) -> MCPCallResponse:
    from plugins.rss.backend import service

    url = (args.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return _err("url 必须是 http/https")
    async with async_session() as db:
        feed = await service.create_feed(db, user_id, url)
        count = await service.fetch_feed_content(db, feed)
        await db.commit()
        await db.refresh(feed)
    return _ok(f"已添加订阅 #{feed.id}：{feed.title or feed.url}，新增 {count} 条")


async def rss_delete_feed(user_id: int, args: dict) -> MCPCallResponse:
    from plugins.rss.backend import service

    try:
        feed_id = _int(args, "feed_id")
    except ValueError as e:
        return _err(str(e))
    async with async_session() as db:
        ok = await service.delete_feed(db, user_id, feed_id)
        await db.commit()
    if not ok:
        return _err(f"订阅 #{feed_id} 不存在")
    return _ok(f"已删除订阅 #{feed_id}")


async def rss_refresh_feed(user_id: int, args: dict) -> MCPCallResponse:
    from plugins.rss.backend import service

    async with async_session() as db:
        feeds = await service.list_feeds(db, user_id)
        if args.get("feed_id"):
            feed_id = int(args["feed_id"])
            feeds = [f for f in feeds if f.id == feed_id]
        total = 0
        for feed in feeds:
            total += await service.fetch_feed_content(db, feed)
        await db.commit()
    return _ok(f"已刷新 {len(feeds)} 个订阅，新增 {total} 条")


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    (
        MCPTool(name="todo_update", description="修改待办事项的标题、描述、状态、优先级、截止时间或标签。",
                inputSchema={"type": "object", "properties": {
                    "todo_id": {"type": "integer"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "status": {"type": "string", "description": "pending / in_progress / done"},
                    "priority": {"type": "integer"},
                    "due_date": {"type": "string", "description": "ISO 时间"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                }, "required": ["todo_id"]}),
        todo_update,
    ),
    (
        MCPTool(name="todo_complete", description="把待办事项标记为已完成。",
                inputSchema={"type": "object", "properties": {"todo_id": {"type": "integer"}}, "required": ["todo_id"]}),
        todo_complete,
    ),
    (
        MCPTool(name="todo_delete", description="删除一个待办事项。",
                inputSchema={"type": "object", "properties": {"todo_id": {"type": "integer"}}, "required": ["todo_id"]}),
        todo_delete,
    ),
    (
        MCPTool(name="event_update", description="修改日程的标题、开始/结束时间、备注或提醒时间。",
                inputSchema={"type": "object", "properties": {
                    "event_id": {"type": "integer"},
                    "title": {"type": "string"},
                    "start_time": {"type": "string", "description": "ISO 时间"},
                    "end_time": {"type": "string", "description": "ISO 时间"},
                    "notes": {"type": "string"},
                    "color": {"type": "string"},
                    "remind_before": {"type": "integer"},
                }, "required": ["event_id"]}),
        event_update,
    ),
    (
        MCPTool(name="event_delete", description="删除/取消一个日程。",
                inputSchema={"type": "object", "properties": {"event_id": {"type": "integer"}}, "required": ["event_id"]}),
        event_delete,
    ),
    (
        MCPTool(name="note_update", description="修改笔记的标题、正文、父目录或图标。",
                inputSchema={"type": "object", "properties": {
                    "note_id": {"type": "integer"},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "parent_id": {"type": "integer"},
                    "icon": {"type": "string"},
                    "sort_order": {"type": "integer"},
                }, "required": ["note_id"]}),
        note_update,
    ),
    (
        MCPTool(name="note_delete", description="删除一篇笔记。",
                inputSchema={"type": "object", "properties": {"note_id": {"type": "integer"}}, "required": ["note_id"]}),
        note_delete,
    ),
    (
        MCPTool(name="notification_mark_read", description="把一条通知标记为已读。",
                inputSchema={"type": "object", "properties": {"notification_id": {"type": "integer"}}, "required": ["notification_id"]}),
        notification_mark_read,
    ),
    (
        MCPTool(name="notification_mark_all_read", description="把所有通知标记为已读。",
                inputSchema={"type": "object", "properties": {}}),
        notification_mark_all_read,
    ),
    (
        MCPTool(name="notification_send", description="给当前用户发送一条站内通知。",
                inputSchema={"type": "object", "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "link": {"type": "string"},
                }, "required": ["title"]}),
        notification_send,
    ),
    (
        MCPTool(name="memory_list", description="列出当前 Bot 的长期记忆。",
                inputSchema={"type": "object", "properties": {
                    "limit": {"type": "integer"},
                    "kind": {"type": "string"},
                }}),
        memory_list,
    ),
    (
        MCPTool(name="memory_delete", description="删除当前 Bot 的一条长期记忆。",
                inputSchema={"type": "object", "properties": {"memory_id": {"type": "integer"}}, "required": ["memory_id"]}),
        memory_delete,
    ),
    (
        MCPTool(name="file_delete", description="删除文件或文件夹；默认移入回收站，permanent=true 时永久删除。",
                inputSchema={"type": "object", "properties": {
                    "file_id": {"type": "integer"},
                    "permanent": {"type": "boolean", "description": "默认 false，移入回收站"},
                }, "required": ["file_id"]}),
        file_delete,
    ),
    (
        MCPTool(name="file_rename", description="重命名文件或文件夹。",
                inputSchema={"type": "object", "properties": {
                    "file_id": {"type": "integer"},
                    "new_name": {"type": "string"},
                }, "required": ["file_id", "new_name"]}),
        file_rename,
    ),
    (
        MCPTool(name="file_move", description="把文件或文件夹移动到另一个目录。",
                inputSchema={"type": "object", "properties": {
                    "file_id": {"type": "integer"},
                    "folder_path": {"type": "string", "description": "目标目录，例如 /docs"},
                }, "required": ["file_id", "folder_path"]}),
        file_move,
    ),
    (
        MCPTool(name="file_create_folder", description="在文件库中新建文件夹。",
                inputSchema={"type": "object", "properties": {
                    "name": {"type": "string"},
                    "parent_path": {"type": "string", "description": "父目录，默认 /"},
                }, "required": ["name"]}),
        file_create_folder,
    ),
    (
        MCPTool(name="read_file_content", description="读取文件库中的 PDF / Word / Excel / 文本文件正文。先用 search_files 或 list_files 找 file_id。",
                inputSchema={"type": "object", "properties": {
                    "file_id": {"type": "integer"},
                    "max_chars": {"type": "integer"},
                }, "required": ["file_id"]}),
        read_file_content,
    ),
    (
        MCPTool(name="mail_read", description="读取一封已同步邮件的完整正文。先用 list_recent_emails 找 mail_id。",
                inputSchema={"type": "object", "properties": {"mail_id": {"type": "integer"}}, "required": ["mail_id"]}),
        mail_read,
    ),
    (
        MCPTool(name="send_email", description="使用用户配置的邮箱发送邮件。",
                inputSchema={"type": "object", "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "account_id": {"type": "integer"},
                }, "required": ["to", "subject"]}),
        mail_send,
    ),
    (
        MCPTool(name="project_create", description="添加一个代码项目。路径留空时默认 /workspace/<名称>；Git 项目必须提供仓库地址。",
                inputSchema={"type": "object", "properties": {
                    "name": {"type": "string"},
                    "path": {"type": "string"},
                    "is_git": {"type": "boolean"},
                    "repo_url": {"type": "string"},
                    "default_branch": {"type": "string"},
                    "description": {"type": "string"},
                }, "required": ["name"]}),
        project_create,
    ),
    (
        MCPTool(name="project_update", description="修改项目的名称、路径、Git 属性、仓库地址或默认分支。",
                inputSchema={"type": "object", "properties": {
                    "project_id": {"type": "integer"},
                    "name": {"type": "string"},
                    "path": {"type": "string"},
                    "is_git": {"type": "boolean"},
                    "repo_url": {"type": "string"},
                    "default_branch": {"type": "string"},
                    "description": {"type": "string"},
                }, "required": ["project_id"]}),
        project_update,
    ),
    (
        MCPTool(name="project_delete", description="删除项目记录及其项目目录，不可恢复。",
                inputSchema={"type": "object", "properties": {"project_id": {"type": "integer"}}, "required": ["project_id"]}),
        project_delete,
    ),
    (
        MCPTool(name="routine_list", description="列出当前 Bot 的例程（定时/事件触发）。",
                inputSchema={"type": "object", "properties": {}}),
        routine_list,
    ),
    (
        MCPTool(name="routine_create", description="为当前 Bot 创建例程。cron_expr 使用 5 段 cron，例如 0 7 * * *。",
                inputSchema={"type": "object", "properties": {
                    "name": {"type": "string"},
                    "trigger_type": {"type": "string", "enum": ["cron", "event", "manual"]},
                    "cron_expr": {"type": "string"},
                    "event_type": {"type": "string"},
                    "event_filter": {"type": "object"},
                    "prompt": {"type": "string"},
                    "enabled": {"type": "boolean"},
                }, "required": ["name"]}),
        routine_create,
    ),
    (
        MCPTool(name="routine_update", description="修改例程的名称、cron、触发事件、提示词或启用状态。",
                inputSchema={"type": "object", "properties": {
                    "routine_id": {"type": "integer"},
                    "name": {"type": "string"},
                    "trigger_type": {"type": "string"},
                    "cron_expr": {"type": "string"},
                    "event_type": {"type": "string"},
                    "event_filter": {"type": "object"},
                    "prompt": {"type": "string"},
                    "enabled": {"type": "boolean"},
                }, "required": ["routine_id"]}),
        routine_update,
    ),
    (
        MCPTool(name="routine_delete", description="删除一个例程。",
                inputSchema={"type": "object", "properties": {"routine_id": {"type": "integer"}}, "required": ["routine_id"]}),
        routine_delete,
    ),
    (
        MCPTool(name="routine_run", description="立即执行一次例程。",
                inputSchema={"type": "object", "properties": {"routine_id": {"type": "integer"}}, "required": ["routine_id"]}),
        routine_run,
    ),
    (
        MCPTool(name="rss_list_feeds", description="列出 RSS 订阅。",
                inputSchema={"type": "object", "properties": {}}),
        rss_list_feeds,
    ),
    (
        MCPTool(name="rss_add_feed", description="添加 RSS/Atom 订阅并立即抓取。",
                inputSchema={"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}),
        rss_add_feed,
    ),
    (
        MCPTool(name="rss_delete_feed", description="删除一个 RSS 订阅。",
                inputSchema={"type": "object", "properties": {"feed_id": {"type": "integer"}}, "required": ["feed_id"]}),
        rss_delete_feed,
    ),
    (
        MCPTool(name="rss_refresh_feed", description="刷新 RSS 订阅；不传 feed_id 时刷新全部。",
                inputSchema={"type": "object", "properties": {"feed_id": {"type": "integer"}}}),
        rss_refresh_feed,
    ),
]
