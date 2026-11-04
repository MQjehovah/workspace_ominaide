"""Daily scheduler: generate briefing at 9:30 AM and push as notification."""
import asyncio
from time import time as _clock
from datetime import datetime, time

BRIEFING_HOUR = 9
BRIEFING_MINUTE = 30
CHECK_INTERVAL = 60  # seconds between checks

_sent_today: set[int] = set()  # track which user_ids got briefing today


async def _send_briefing(user_id: int):
    """Build a data-grounded morning brief and push it to web + device."""
    try:
        from datetime import datetime, timedelta
        from sqlalchemy import select, func
        from core.config.settings import settings
        from core.database.session import async_session
        from plugins.schedule.backend.models import Event
        from plugins.todo.backend.models import PluginTodoItem
        from plugins.notifications.backend.models import Notification
        from plugins.rss.backend.models import Entry, Feed
        from plugins.notifications.backend.service import create_notification

        now = datetime.now()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        async with async_session() as db:
            events = list((await db.execute(
                select(Event).where(
                    Event.user_id == user_id,
                    Event.start_time >= day_start,
                    Event.start_time < day_end,
                ).order_by(Event.start_time)
            )).scalars().all())

            todos = list((await db.execute(
                select(PluginTodoItem).where(
                    PluginTodoItem.user_id == user_id,
                    PluginTodoItem.status != "done",
                ).order_by(PluginTodoItem.priority.desc(), PluginTodoItem.due_date.asc()).limit(6)
            )).scalars().all())

            unread = (await db.execute(
                select(func.count(Notification.id)).where(
                    Notification.user_id == user_id,
                    Notification.read == False,
                )
            )).scalar() or 0

            since = now - timedelta(hours=24)
            rss = list((await db.execute(
                select(Entry).join(Feed, Entry.feed_id == Feed.id).where(
                    Feed.user_id == user_id,
                    Entry.published >= since,
                    Entry.read == False,
                ).order_by(Entry.published.desc()).limit(5)
            )).scalars().all())

        weather = None
        try:
            from plugins.device.backend.router import _current_weather
            weather = await _current_weather()
        except Exception:
            pass

        wmo = {
            0: "晴", 1: "晴间多云", 2: "多云", 3: "阴", 45: "雾", 48: "雾凇",
            51: "小毛雨", 53: "毛雨", 55: "大毛雨", 61: "小雨", 63: "中雨",
            65: "大雨", 71: "小雪", 73: "中雪", 75: "大雪", 80: "阵雨",
            81: "强阵雨", 82: "暴雨", 95: "雷雨", 96: "雷雨冰雹",
        }
        weather_text = ""
        if weather:
            weather_text = f"{weather.get('temp')}℃，{wmo.get(int(weather.get('code') or -1), '天气未知')}"
        weather_line = f"天气：{weather_text}\n" if weather_text else ""

        ev_lines = [
            f"{e.start_time.strftime('%H:%M')} {e.title}" for e in events
        ] or ["今天没有日程"]
        todo_lines = [t.title for t in todos] or ["没有未完成待办"]
        rss_lines = [e.title for e in rss] or ["没有新的订阅文章"]

        data = (
            f"日期：{now.strftime('%Y-%m-%d 星期') + '日一二三四五六'[now.weekday()]}\n"
            f"{weather_line}"
            f"今日日程：{'；'.join(ev_lines)}\n"
            f"未完成待办：{'；'.join(todo_lines)}\n"
            f"未读通知：{unread} 条\n"
            f"新订阅文章：{'；'.join(rss_lines)}"
        )

        briefing = ""
        if settings.llm_api_key:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
            resp = await client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": (
                        "你是用户的私人助理，正在生成每天早上主动播报的晨间简报。\n"
                        "根据给定数据写 3-6 句中文口语化简报：先问候，结合天气给出穿衣/带伞建议，"
                        "再概括今日日程和最重要的 1-2 个待办，最后用一句提醒今天最先要做的事。\n"
                        "要求：不要 Markdown、不要标题、不要列表、不要编造数据；没有数据就自然略过。"
                    )},
                    {"role": "user", "content": data},
                ],
                temperature=0.4,
            )
            briefing = (resp.choices[0].message.content or "").strip()
        if not briefing:
            briefing = (
                f"早上好。今天{weather_text}。"
                f"今日日程：{'；'.join(ev_lines)}。"
                f"待办：{'；'.join(todo_lines)}。"
            )

        async with async_session() as db:
            n = await create_notification(
                db, user_id, "☀️ 晨间简报", briefing[:4000], "briefing", "/notes"
            )
            await db.commit()
            nid = n.id

        # Web/desktop notification channel.
        try:
            from core.wschannel.hub import host_channel
            await host_channel.broadcast(user_id, "notifications", {
                "type": "new_notification", "id": nid,
                "title": "☀️ 晨间简报", "body": briefing,
            })
        except Exception:
            pass

        # Device: a compact event, the device fetches the full body + TTS.
        try:
            from plugins.device.backend.events import publish_device_event
            await publish_device_event(user_id, "briefing", {
                "id": nid, "title": "☀️ 晨间简报",
            })
        except Exception as e:
            print(f"[scheduler] briefing device push error: {e}")

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
                    from plugins.notifications.backend.router import notify_user
                    await notify_user(ev.user_id, {"type": "new_notification", "title": f"⏰ 日程提醒: {ev.title}"})
                except Exception:
                    pass
    except Exception as e:
        print(f"[scheduler] reminder error: {e}")


EVENT_SCAN_INTERVAL = 15 * 60  # seconds between LLM scans of the event stream
_last_event_scan = 0.0
# Composite cursor (created_at, id) — advances precisely so batches never lose
# events (when more than the limit arrive at once) nor re-read old ones.
_last_event_cursor = None

DAILY_SCAN_INTERVAL = 24 * 60 * 60  # seconds between daily preference/memory analyses
_last_daily_scan = 0.0
_last_daily_scan_date = None  # date string of the last daily analysis

MAX_EVENTS_PER_BATCH = 40  # cap for a single LLM batch (prevent prompt overflow)


async def _fetch_new_events(db, cursor, limit=MAX_EVENTS_PER_BATCH):
    from sqlalchemy import select, or_, and_
    from core.events.models import UserActivity
    q = select(UserActivity).where(
        ~UserActivity.event_type.like("device.%")
    ).order_by(UserActivity.id).limit(limit)
    if cursor:
        cursor_ts, cursor_id = cursor
        q = q.where(or_(
            UserActivity.created_at > cursor_ts,
            and_(UserActivity.created_at == cursor_ts, UserActivity.id > cursor_id),
        ))
    r = await db.execute(q)
    return list(r.scalars().all())


async def _scan_events():
    """Review ONLY events that happened since the last scan.

    - No new events      -> skip entirely, no LLM call.
    - New events (capped) -> one batched LLM call; notify ONLY if genuinely important.
      The cursor advances to the last processed event, so a burst larger than the
      cap is picked up in the following scans instead of overflowing the prompt.
    """
    from core.config.settings import settings
    if not settings.llm_api_key:
        return
    from datetime import datetime
    from core.database.session import async_session

    global _last_event_cursor

    now = datetime.utcnow()
    cursor = _last_event_cursor
    if cursor is None:
        # First scan (or after restart): only today's events — never read the whole history.
        cursor = (now.replace(hour=0, minute=0, second=0, microsecond=0), 0)

    try:
        async with async_session() as db:
            events = await _fetch_new_events(db, cursor)
            if not events:
                _last_event_cursor = (now, 0)
                return  # nothing new — don't call the LLM

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
                        "你是一个个人AI助手。下面是一段时间内用户的行为事件记录，每条带时间戳[MM-DD HH:MM]。"
                        "请直接判断【是否需要给用户发送一条提醒通知】，注意区分事件的新旧："
                        "只把【最近 1-2 小时内发生且需要立即处理】的事项当作需要通知（如刚到的紧急邮件、即将到来的截止、刚发生的异常）。"
                        "几小时前或更早的常规事件（如今天早些时候收到的邮件、早上的文件上传）属于历史，一律不要提醒。"
                        "需要通知的情况：刚刚发生的紧急任务/截止期限临近、刚到的重要客户或领导邮件、需要用户尽快处理或决策的事、异常或错误。"
                        "不需要通知的情况：历史事件、日常普通操作（普通上传、普通笔记编辑、常规订阅等）、或无需打扰用户。"
                        "只返回 JSON，格式: {\"notify\": true/false, \"summary\": \"通知内容(简短中文2-4句，仅当notify为true时)或空字符串\"}。"
                        "不要输出其他内容。"
                    )},
                    {"role": "user", "content": batch},
                ],
                temperature=0.1,
            )
            raw = resp.choices[0].message.content or ""
            m = re.search(r"\{.*\}", raw, re.S)
            notify = False
            summary = ""
            if m:
                try:
                    data = _json.loads(m.group(0))
                    notify = bool(data.get("notify", data.get("important", False)))
                    summary = str(data.get("summary") or "").strip()
                except Exception:
                    pass

            # Advance the cursor past everything we just processed.
            last = events[-1]
            _last_event_cursor = (last.created_at, last.id)
            if not notify or not summary:
                return  # LLM decided no notification is needed

            from plugins.notifications.backend.service import create_notification
            from plugins.notifications.backend.router import notify_user
            n = await create_notification(
                db, last.user_id,
                "🔔 重要事项提醒",
                summary,
                "important",
                "/",
            )
            await db.commit()
            try:
                await notify_user(last.user_id, {
                    "type": "new_notification",
                    "id": n.id,
                    "title": "🔔 重要事项提醒",
                    "body": summary,
                })
            except Exception:
                pass
    except Exception as e:
        print(f"[scheduler] event scan error: {e}")


async def _daily_event_analysis():
    """Run once a day: analyse the day's events to update user preferences / permanent memory.

    Processes events in capped batches so a busy day can't overflow the prompt.
    """
    from core.config.settings import settings
    if not settings.llm_api_key:
        return
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from core.events.models import UserActivity
    from core.database.session import async_session
    from core.auth.domain.models import UserProfile

    now = datetime.utcnow()
    since = now - timedelta(hours=24)
    try:
        async with async_session() as db:
            r = await db.execute(
                select(UserActivity).where(UserActivity.created_at >= since).order_by(UserActivity.id)
            )
            events = list(r.scalars().all())
            if not events:
                return

            from openai import AsyncOpenAI
            import json as _json
            import re
            client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)

            # Accumulated profile data merged across batches.
            merged = {"interests": [], "projects": [], "habits": [], "preferences": {}}
            user_ids = set()

            for i in range(0, len(events), MAX_EVENTS_PER_BATCH):
                chunk = events[i:i + MAX_EVENTS_PER_BATCH]
                user_ids.update(e.user_id for e in chunk)
                items = []
                for e in chunk:
                    ts = e.created_at.strftime("%m-%d %H:%M") if e.created_at else ""
                    items.append(f"[{ts}] {e.event_type}: {e.summary or ''}")
                batch = "\n".join(items)

                resp = await client.chat.completions.create(
                    model=settings.llm_model,
                    messages=[
                        {"role": "system", "content": (
                            "你是一个个人AI助手，负责从用户的行为事件中提取长期有效的用户画像与偏好，用于永久记忆。"
                            "分析：用户关注的项目/领域、常用工具与工作习惯、重要联系人/团队、时间安排规律、兴趣偏好、"
                            "需要记住的长期事项。只返回 JSON，格式: "
                            "{\"interests\": [\"兴趣/领域\"], \"projects\": [{\"name\": \"项目名\", \"status\": \"进行中/已完成\"}], "
                            "\"habits\": [\"工作习惯\"], \"preferences\": {\"偏好键\": \"值\"}}。不要输出其他内容。"
                        )},
                        {"role": "user", "content": batch},
                    ],
                    temperature=0.2,
                )
                raw = resp.choices[0].message.content or ""
                m = re.search(r"\{.*\}", raw, re.S)
                if not m:
                    continue
                try:
                    data = _json.loads(m.group(0))
                except Exception:
                    continue
                merged["interests"].extend(data.get("interests") or [])
                merged["habits"].extend(data.get("habits") or [])
                merged["projects"].extend(data.get("projects") or [])
                if isinstance(data.get("preferences"), dict):
                    merged["preferences"].update(data["preferences"])

            # De-duplicate accumulated lists.
            merged["interests"] = list(dict.fromkeys(merged["interests"]))
            merged["habits"] = list(dict.fromkeys(merged["habits"]))
            seen = set()
            projects = []
            for p in merged["projects"]:
                name = (p.get("name") if isinstance(p, dict) else str(p))
                if name and name not in seen:
                    seen.add(name)
                    projects.append(p)
            merged["projects"] = projects

            # Update the user's profile preferences (long-term memory).
            for uid in user_ids:
                pr = (await db.execute(select(UserProfile).where(UserProfile.user_id == uid))).scalar_one_or_none()
                if pr is None:
                    continue
                prefs = {}
                try:
                    if pr.preferences:
                        prefs = _json.loads(pr.preferences) if isinstance(pr.preferences, str) else pr.preferences
                except Exception:
                    prefs = {}
                prefs["last_analysis"] = now.isoformat()
                prefs["interests"] = merged["interests"] or prefs.get("interests", [])
                prefs["habits"] = merged["habits"] or prefs.get("habits", [])
                if merged["projects"]:
                    prefs["projects"] = merged["projects"]
                if merged["preferences"]:
                    prefs["profile"] = merged["preferences"]
                pr.preferences = _json.dumps(prefs, ensure_ascii=False)
            await db.commit()
            print(f"[scheduler] daily analysis done ({len(events)} events, {len(merged['projects'])} projects)")

            # Turn the dormant insight engine on: mine 30-day patterns and store
            # them in profile.preferences.insights for proactive suggestions.
            if settings.intelligence_layer_enabled and user_ids:
                from core.ai.insights import discover_insights
                for uid in sorted(user_ids):
                    try:
                        await discover_insights(uid)
                    except Exception as e:
                        print(f"[scheduler] insights error for user {uid}: {e}")
    except Exception as e:
        print(f"[scheduler] daily analysis error: {e}")


async def scheduler_loop():
    """Background loop: check time every 60s, trigger briefing at 9:30, event reminders,
    periodic event scanning, and once-daily preference/memory analysis."""
    global _last_event_scan, _last_daily_scan, _last_daily_scan_date
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

            if _last_daily_scan_date != today_key and _clock() - _last_daily_scan >= DAILY_SCAN_INTERVAL:
                _last_daily_scan = _clock()
                _last_daily_scan_date = today_key
                await _daily_event_analysis()

            from core.config.settings import settings as _settings
            if (_settings.morning_brief_enabled
                    and now.hour == _settings.morning_brief_hour
                    and now.minute == _settings.morning_brief_minute):
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

                # The morning briefing is routine-driven once a Bot routine
                # exists; this hard-coded path is only a fallback.
                if active_users:
                    try:
                        from core.bots.routines import has_enabled_routine

                        active_users = [
                            uid
                            for uid in active_users
                            if not await has_enabled_routine(uid, "morning_brief")
                        ]
                    except Exception:
                        pass

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
