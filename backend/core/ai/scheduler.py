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
    q = select(UserActivity).order_by(UserActivity.id).limit(limit)
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
            from plugins.notifications.backend.router import ws_manager
            n = await create_notification(
                db, last.user_id,
                "🔔 重要事项提醒",
                summary,
                "important",
                "/",
            )
            await db.commit()
            try:
                await ws_manager.notify_user(last.user_id, {
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
