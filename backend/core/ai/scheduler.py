"""Daily scheduler: generate briefing at 9:30 AM and push as notification."""
import asyncio
from time import time as _clock
from datetime import datetime, time

BRIEFING_HOUR = 9
BRIEFING_MINUTE = 30
CHECK_INTERVAL = 60  # seconds between checks

_sent_today: set[int] = set()  # track which user_ids got briefing today


async def _send_briefing(user_id: int):
    """Generate briefing via agent and save as notification."""
    try:
        from core.ai.agent import run_agent
        from plugins.chat.backend.memory import build_context

        ctx = await build_context(user_id)
        messages = []
        if ctx:
            messages.append({"role": "system", "content": ctx})
        messages.append({"role": "system", "content": "你是一个主动的个人AI助理。用户请求每日简报。请调用工具获取相关信息，然后生成一段友好、简洁的简报，总结今日日程、未读通知和新文章。用中文。如果今天没有待办事项和未读通知，就简短问候。"})
        messages.append({"role": "user", "content": "帮我生成今天的每日简报"})

        briefing = await run_agent(user_id, messages)

        # Save as notification
        from plugins.notifications.backend.service import create_notification
        from core.database.session import async_session

        async with async_session() as db:
            await create_notification(db, user_id, "📋 每日简报", briefing[:300], "briefing", f"/api/activities?event_type=briefing")
            await db.commit()

        # Push via WebSocket if manager is available
        try:
            from plugins.notifications.backend.router import ws_manager
            await ws_manager.notify_user(user_id, {"type": "new_notification", "title": "📋 每日简报"})
        except Exception:
            pass

        _sent_today.add(user_id)
    except Exception as e:
        print(f"[scheduler] briefing error for user {user_id}: {e}")


async def _check_reminders():
    """Check for upcoming schedule events and push reminder notifications."""
    from datetime import timedelta
    from sqlalchemy import select
    from plugins.schedule.backend.models import Event
    from plugins.notifications.backend.service import create_notification
    from core.database.session import async_session

    now = datetime.now()
    window = now + timedelta(minutes=15)
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

            reminded: list[Event] = []
            for ev in events:
                delta_min = (ev.start_time - now).total_seconds() / 60
                if delta_min <= ev.remind_before:
                    await create_notification(
                        db, ev.user_id,
                        f"⏰ 日程提醒: {ev.title}",
                        f"{ev.start_time.strftime('%m-%d %H:%M')} 开始",
                        "reminder",
                        "/schedule",
                    )
                    ev.reminded = True
                    reminded.append(ev)
            await db.commit()

            for ev in reminded:
                try:
                    from plugins.notifications.backend.router import ws_manager
                    await ws_manager.notify_user(ev.user_id, {"type": "new_notification", "title": f"⏰ 日程提醒: {ev.title}"})
                except Exception:
                    pass
    except Exception as e:
        print(f"[scheduler] reminder error: {e}")


EVENT_SCAN_INTERVAL = 15 * 60  # seconds between LLM scans of the event stream
_last_event_scan = 0.0
_last_event_cursor = None  # datetime cursor of the last scanned event


async def _scan_events():
    """Periodically ask the LLM to review ALL recent user events and summarize
    anything important into a notification.

    Covers every recorded activity (file uploads, todo changes, schedule,
    new mail, etc.). Batches new events since the last scan into one LLM call;
    if anything is important, pushes a single summary notification over WebSocket.
    """
    from core.config.settings import settings
    if not settings.llm_api_key:
        return
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from core.events.models import UserActivity
    from core.database.session import async_session

    global _last_event_cursor

    now = datetime.utcnow()
    cursor = _last_event_cursor
    if cursor is None:
        cursor = now - timedelta(hours=3)  # first scan: look back a few hours

    try:
        async with async_session() as db:
            r = await db.execute(
                select(UserActivity)
                .where(UserActivity.created_at > cursor)
                .order_by(UserActivity.created_at)
                .limit(40)
            )
            events = list(r.scalars().all())
            if not events:
                _last_event_cursor = now
                return

            items = []
            for e in events:
                ts = e.created_at.strftime("%m-%d %H:%M") if e.created_at else ""
                detail = ""
                if e.details:
                    try:
                        import json as _j
                        detail = " " + _j.dumps(e.details, ensure_ascii=False)[:200]
                    except Exception:
                        pass
                items.append(f"[{ts}] {e.event_type}: {e.summary or ''}{detail}")
            batch = "\n".join(items)

            from openai import AsyncOpenAI
            import json as _json
            import re
            client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
            resp = await client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": (
                        "你是一个个人AI助手。下面是一段时间内用户的行为事件记录（文件操作、待办、日程、新邮件等）。"
                        "请找出其中重要、需要用户注意的事项（紧急事务、截止期限、重要邮件、关键变更、异常等），"
                        "并用中文写一段简短总结（3-5 句话）。"
                        "只返回 JSON，格式: {\"important\": true/false, \"summary\": \"总结内容\"}。"
                        "若没有重要事项返回 {\"important\": false}。不要输出其他内容。"
                    )},
                    {"role": "user", "content": batch},
                ],
                temperature=0.1,
            )
            raw = resp.choices[0].message.content or ""
            m = re.search(r"\{.*\}", raw, re.S)
            important = False
            summary = ""
            if m:
                try:
                    data = _json.loads(m.group(0))
                    important = bool(data.get("important"))
                    summary = str(data.get("summary") or "").strip()
                except Exception:
                    pass

            _last_event_cursor = events[-1].created_at
            await db.commit()

            if not important or not summary:
                return

            from plugins.notifications.backend.service import create_notification
            from plugins.notifications.backend.router import ws_manager
            n = await create_notification(
                db, events[-1].user_id,
                "🔔 重要事项提醒",
                summary,
                "important",
                "/",
            )
            await db.commit()
            try:
                await ws_manager.notify_user(events[-1].user_id, {
                    "type": "new_notification",
                    "id": n.id,
                    "title": "🔔 重要事项提醒",
                    "body": summary,
                })
            except Exception:
                pass
    except Exception as e:
        print(f"[scheduler] event scan error: {e}")


async def scheduler_loop():
    """Background loop: check time every 60s, trigger briefing at 9:30 and event reminders."""
    global _last_event_scan
    while True:
        try:
            now = datetime.now()
            today_key = now.date().isoformat()

            # Reset sent tracking at midnight
            if _sent_today and _sent_today_date() != today_key:
                _sent_today.clear()

            await _check_reminders()

            if _clock() - _last_event_scan >= EVENT_SCAN_INTERVAL:
                _last_event_scan = _clock()
                await _scan_events()

            if now.hour == BRIEFING_HOUR and now.minute == BRIEFING_MINUTE:
                # Collect users who have recent activity (active in last 7 days)
                try:
                    from sqlalchemy import select, func
                    from core.events.models import UserActivity
                    from core.database.session import async_session
                    from datetime import timedelta

                    since = now - timedelta(days=7)
                    async with async_session() as db:
                        r = await db.execute(
                            select(UserActivity.user_id).where(UserActivity.created_at >= since).distinct()
                        )
                        active_users = [row[0] for row in r.fetchall() if row[0] not in _sent_today]
                except Exception:
                    active_users = []

                if active_users:
                    tasks = [_send_briefing(uid) for uid in active_users]
                    await asyncio.gather(*tasks)
                    # Wait a minute to avoid re-triggering
                    await asyncio.sleep(120)
        except Exception as e:
            print(f"[scheduler] error: {e}")

        await asyncio.sleep(CHECK_INTERVAL)


def _sent_today_date() -> str:
    return datetime.now().date().isoformat()
