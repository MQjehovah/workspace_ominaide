"""Background loop for non-AI work: reminders + mail/资讯 fetching.

Scheduled LLM jobs (event scan, profile refresh, morning brief, daily review,
资讯 digest) intentionally live in the Bot routine system instead, so every token
spend is visible and can be paused from Bot Console.

One exception: the workbench daily brief is rendered once per hour here and
cached, because the mobile first paint must never wait for an LLM call.
"""

from core.logging import get_logger
log = get_logger(__name__)
import asyncio
from time import time as _clock
from datetime import datetime, timedelta

CHECK_INTERVAL = 60  # seconds between checks

_last_mail_sync = 0.0
_last_sources_refresh = 0.0
_last_brief_generation = 0.0
_brief_task: asyncio.Task | None = None


async def _refresh_briefs() -> None:
    """Render the hourly daily-brief snapshot for every user."""
    try:
        from core.skills.brief_cache import refresh_all

        result = await refresh_all()
        log.info(
            f"[scheduler] daily briefs rendered: "
            f"{result['generated']} ok, {result['failed']} failed"
        )
    except Exception as e:
        log.warning(f"[scheduler] daily brief render error: {e}")


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
                except Exception as exc:
                    log.warning("notification push failed for user %s: %s", user_id, exc)
    except Exception as e:
        log.warning(f"[scheduler] reminder error: {e}")


async def _sync_mail() -> None:
    """Backend-first mail: pull due IMAP accounts even with no desktop online."""
    try:
        from core.config.settings import settings as _settings
        from plugins.mail.backend.sync import sync_due_accounts

        result = await sync_due_accounts(_settings.mail_sync_interval_seconds)
        if result.get("new"):
            log.info(f"[scheduler] mail synced: {result['new']} new message(s)")
    except Exception as e:
        log.warning(f"[scheduler] mail sync error: {e}")


async def _refresh_sources() -> None:
    """Backend-first information sources: refresh on a timer, independent of clients."""
    try:
        from sqlalchemy import or_, select
        from core.config.settings import settings as _settings
        from core.database.session import async_session
        from plugins.sources.backend.models import ContentSource
        from plugins.sources.backend.service import fetch_source_content

        cutoff = datetime.utcnow() - timedelta(seconds=_settings.sources_refresh_interval_seconds)
        async with async_session() as db:
            r = await db.execute(
                select(ContentSource.id).where(
                    or_(ContentSource.last_fetch == None, ContentSource.last_fetch < cutoff)  # noqa: E711
                )
            )
            source_ids = [row[0] for row in r.all()]

        for source_id in source_ids:
            async with async_session() as db:
                source = (await db.execute(
                    select(ContentSource).where(ContentSource.id == source_id)
                )).scalar_one_or_none()
                if source is None:
                    continue
                try:
                    new = await fetch_source_content(db, source)
                    await db.commit()
                    if new:
                        log.info(f"[scheduler] sources {source.url}: {new} new")
                except Exception as e:
                    await db.rollback()
                    log.warning(f"[scheduler] sources refresh error {source_id}: {e}")
    except Exception as e:
        log.warning(f"[scheduler] sources refresh loop error: {e}")


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


async def scheduler_loop():
    """Check every 60s. Reminders and background syncing run here; the hourly
    daily-brief snapshot is the single LLM job scheduled from this loop."""
    global _last_mail_sync, _last_sources_refresh, _last_brief_generation, _brief_task
    while True:
        try:
            await _check_reminders()

            if _clock() - _last_brief_generation >= 3600:
                _last_brief_generation = _clock()
                if _brief_task is None or _brief_task.done():
                    _brief_task = asyncio.create_task(_refresh_briefs())

            from core.config.settings import settings as _settings

            if _settings.mail_sync_enabled and _clock() - _last_mail_sync >= _settings.mail_sync_interval_seconds:
                _last_mail_sync = _clock()
                await _sync_mail()

            if _settings.sources_refresh_enabled and _clock() - _last_sources_refresh >= _settings.sources_refresh_interval_seconds:
                _last_sources_refresh = _clock()
                await _refresh_sources()

        except Exception as e:
            log.warning(f"[scheduler] error: {e}")

        await asyncio.sleep(CHECK_INTERVAL)
