"""Daily scheduler: generate briefing at 9:30 AM and push as notification."""
import asyncio
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


async def scheduler_loop():
    """Background loop: check time every 60s, trigger briefing at 9:30."""
    while True:
        try:
            now = datetime.now()
            today_key = now.date().isoformat()

            # Reset sent tracking at midnight
            if _sent_today and _sent_today_date() != today_key:
                _sent_today.clear()

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
