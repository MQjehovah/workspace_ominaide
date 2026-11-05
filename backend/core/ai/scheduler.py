"""Background loop for non-AI work: reminders + mail/RSS fetching.

Scheduled LLM jobs (event scan, profile refresh, morning brief, daily review,
RSS digest) intentionally live in the Bot routine system instead, so every token
spend is visible and can be paused from Bot Console.
"""
import asyncio
from time import time as _clock
from datetime import datetime, timedelta

CHECK_INTERVAL = 60  # seconds between checks

_last_mail_sync = 0.0
_last_rss_refresh = 0.0
_last_dingtalk_sync_date: str | None = None


async def _check_reminders():
    """Check for upcoming schedule events and push reminder notifications."""
    from sqlalchemy import select
    from plugins.schedule.backend.models import Event
    from plugins.notifications.backend.service import create_notification
    from core.database.session import async_session

    now = datetime.now()
    # Honour remind_before up to 24h (the old 15-minute window silently ignored
    # reminders configured for 30/60/1440 minutes before the event).
    window = now + timedelta(hours=24)
    try:
        async with async_session() as db:
            r = await db.execute(
                select(Event).where(
                    Event.reminded == False,
                    Event.remind_before > 0,
                    Event.start_time >= now,
                    Event.start_time <= window,
                )
            )
            events = list(r.scalars().all())

            reminded: list[tuple[int, str, str]] = []
            for ev in events:
                delta_min = (ev.start_time - now).total_seconds() / 60
                if delta_min <= ev.remind_before:
                    await create_notification(
                        db, ev.user_id,
                        f"⏰ 日程提醒: {ev.title}",
                        f"{ev.start_time.strftime('%m-%d %H:%M')} 开始",
                        "reminder",
                        "/schedule",
                        actions=[{"key": "open", "label": "查看日程", "kind": "open", "link": "/schedule"}],
                        dedupe_key=f"schedule:{ev.id}:{ev.start_time.isoformat()}",
                    )
                    ev.reminded = True
                    reminded.append((ev.user_id, f"⏰ 日程提醒: {ev.title}", "/schedule"))

            # Todo deadlines: remind once when the deadline is near or just passed.
            from plugins.todo.backend.models import PluginTodoItem

            todo_window = now + timedelta(minutes=30)
            overdue_floor = now - timedelta(hours=24)
            todo_rows = list((await db.execute(
                select(PluginTodoItem).where(
                    PluginTodoItem.status != "done",
                    PluginTodoItem.reminded == False,
                    PluginTodoItem.due_date != None,
                    PluginTodoItem.due_date <= todo_window,
                    PluginTodoItem.due_date >= overdue_floor,
                )
            )).scalars().all())
            for todo in todo_rows:
                await create_notification(
                    db, todo.user_id,
                    f"⏳ 待办提醒: {todo.title}",
                    f"截止 {todo.due_date.strftime('%m-%d %H:%M')}",
                    "todo_reminder",
                    "/apps/todo",
                    actions=[
                        {"key": "complete", "label": "标记完成", "kind": "complete_todo", "todo_id": todo.id},
                        {"key": "snooze", "label": "10 分钟后", "kind": "snooze", "minutes": 10},
                    ],
                    dedupe_key=f"todo:{todo.id}:{todo.due_date.isoformat()}",
                )
                todo.reminded = True
                reminded.append((todo.user_id, f"⏳ 待办提醒: {todo.title}", "/apps/todo"))

            await db.commit()

            for user_id, title, link in reminded:
                try:
                    from plugins.notifications.backend.router import notify_user
                    await notify_user(user_id, {"type": "new_notification", "title": title, "link": link})
                except Exception:
                    pass
    except Exception as e:
        print(f"[scheduler] reminder error: {e}")


async def _sync_mail() -> None:
    """Backend-first mail: pull due IMAP accounts even with no desktop online."""
    try:
        from core.config.settings import settings as _settings
        from plugins.mail.backend.sync import sync_due_accounts

        result = await sync_due_accounts(_settings.mail_sync_interval_seconds)
        if result.get("new"):
            print(f"[scheduler] mail synced: {result['new']} new message(s)")
    except Exception as e:
        print(f"[scheduler] mail sync error: {e}")


async def _refresh_rss() -> None:
    """Backend-first RSS: refresh feeds on a timer, independent of clients."""
    try:
        from sqlalchemy import or_, select
        from core.config.settings import settings as _settings
        from core.database.session import async_session
        from plugins.rss.backend.models import Feed
        from plugins.rss.backend.service import fetch_feed_content

        cutoff = datetime.utcnow() - timedelta(seconds=_settings.rss_refresh_interval_seconds)
        async with async_session() as db:
            r = await db.execute(
                select(Feed.id).where(
                    or_(Feed.last_fetch == None, Feed.last_fetch < cutoff)
                )
            )
            feed_ids = [row[0] for row in r.all()]

        for feed_id in feed_ids:
            async with async_session() as db:
                feed = (await db.execute(select(Feed).where(Feed.id == feed_id))).scalar_one_or_none()
                if feed is None:
                    continue
                try:
                    new = await fetch_feed_content(db, feed)
                    await db.commit()
                    if new:
                        print(f"[scheduler] rss {feed.url}: {new} new")
                except Exception as e:
                    await db.rollback()
                    print(f"[scheduler] rss refresh error {feed_id}: {e}")
    except Exception as e:
        print(f"[scheduler] rss refresh loop error: {e}")


def _unwrap(payload, key: str):
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    for _ in range(4):
        if isinstance(data, dict) and key in data:
            return data[key]
        if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
            data = data["data"]
            continue
        break
    return []


async def _sync_dingtalk() -> None:
    """No-LLM sync: turn recent DingTalk messages into events for the memory agent."""
    from core.config.settings import settings as _settings

    try:
        from mcp_servers.dingtalk.dws_client import run_dws
        from core.database.session import async_session
        from core.events.bus import record_event
        from core.events.models import UserActivity
        from core.mcp_hub.models import McpServer
        from sqlalchemy import select

        now = datetime.now()
        start = (now - timedelta(hours=_settings.dingtalk_sync_hours)).astimezone().replace(microsecond=0)
        start_iso = start.isoformat()
        end_iso = now.astimezone().replace(microsecond=0).isoformat()

        payload = await run_dws(
            ["chat", "+recent-conversations", "--start", start_iso, "--format", "json"],
            timeout=120,
        )
        conversations = _unwrap(payload, "conversations")
        if not conversations:
            return

        async with async_session() as db:
            users = list((await db.execute(
                select(McpServer.user_id).where(
                    McpServer.slug == "dingtalk", McpServer.enabled == True  # noqa: E712
                )
            )).scalars().all())
        user_ids = sorted(set(users)) or [1]

        for user_id in user_ids:
            existing: set[str] = set()
            async with async_session() as db:
                rows = await db.execute(
                    select(UserActivity.details).where(
                        UserActivity.user_id == user_id,
                        UserActivity.event_type == "dingtalk.message",
                        UserActivity.created_at >= now - timedelta(days=2),
                    )
                )
                for (details,) in rows:
                    if isinstance(details, dict) and details.get("message_id"):
                        existing.add(str(details["message_id"]))

            stored = 0
            for conv in conversations[:50]:
                conv_id = conv.get("conversationId") or conv.get("conversation_id")
                conv_name = conv.get("name") or conv_id or "钉钉会话"
                if not conv_id:
                    continue
                try:
                    msg_payload = await run_dws(
                        [
                            "chat", "+chat-messages",
                            "--conversation-id", str(conv_id),
                            "--start", start_iso, "--end", end_iso,
                            "--order", "asc", "--page-all", "--max-items", "30",
                            "--format", "json",
                        ],
                        timeout=180,
                    )
                except Exception:
                    continue
                messages = _unwrap(msg_payload, "messages") or []
                async with async_session() as db:
                    for msg in messages:
                        message_id = str(msg.get("messageId") or "")
                        if not message_id or message_id in existing:
                            continue
                        text = str(msg.get("text") or "").strip()
                        if not text:
                            continue
                        sender = str(msg.get("sender") or "")
                        await record_event(
                            db, user_id, "dingtalk.message", "dingtalk", None,
                            f"钉钉 · {conv_name} · {sender}",
                            {
                                "conversation": conv_name,
                                "conversation_id": str(conv_id),
                                "sender": sender,
                                "message_id": message_id,
                                "preview": text[:200],
                                "time": str(msg.get("createTime") or ""),
                            },
                        )
                        existing.add(message_id)
                        stored += 1
                        if stored >= _settings.dingtalk_sync_max_messages:
                            break
                    await db.commit()
                if stored >= _settings.dingtalk_sync_max_messages:
                    break
            if stored:
                print(f"[scheduler] dingtalk synced: {stored} message(s) for user {user_id}")
    except Exception as e:
        print(f"[scheduler] dingtalk sync error: {e}")


async def scheduler_loop():
    """Check every 60s. Only reminders and fetching live here — no LLM calls."""
    global _last_mail_sync, _last_rss_refresh, _last_dingtalk_sync_date
    while True:
        try:
            await _check_reminders()

            from core.config.settings import settings as _settings

            if _settings.mail_sync_enabled and _clock() - _last_mail_sync >= _settings.mail_sync_interval_seconds:
                _last_mail_sync = _clock()
                await _sync_mail()

            if _settings.rss_refresh_enabled and _clock() - _last_rss_refresh >= _settings.rss_refresh_interval_seconds:
                _last_rss_refresh = _clock()
                await _refresh_rss()

            if _settings.dingtalk_sync_enabled and _last_dingtalk_sync_date != today_key:
                scheduled = now.replace(
                    hour=_settings.dingtalk_sync_hour,
                    minute=_settings.dingtalk_sync_minute,
                    second=0, microsecond=0,
                )
                if now >= scheduled:
                    _last_dingtalk_sync_date = today_key
                    await _sync_dingtalk()
        except Exception as e:
            print(f"[scheduler] error: {e}")

        await asyncio.sleep(CHECK_INTERVAL)
