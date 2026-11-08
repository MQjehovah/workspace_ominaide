"""Schedule reminder checks owned by the schedule plugin."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from core.database.session import async_session
from core.logging import get_logger
from plugins.notifications.backend.service import create_notification
from plugins.schedule.backend.models import Event

log = get_logger(__name__)


async def check_schedule_reminders() -> dict:
    now = datetime.now()
    window = now + timedelta(hours=24)
    reminded = 0
    async with async_session() as db:
        events = list((await db.execute(
            select(Event).where(
                Event.reminded == False,  # noqa: E712
                Event.remind_before > 0,
                Event.start_time >= now,
                Event.start_time <= window,
            )
        )).scalars().all())

        pushed: list[tuple[int, str, str]] = []
        for event in events:
            delta_min = (event.start_time - now).total_seconds() / 60
            if delta_min > event.remind_before:
                continue
            await create_notification(
                db,
                event.user_id,
                f"⏰ 日程提醒: {event.title}",
                f"{event.start_time.strftime('%m-%d %H:%M')} 开始",
                "reminder",
                "/schedule",
                actions=[{
                    "key": "open",
                    "label": "查看日程",
                    "kind": "open",
                    "link": "/schedule",
                }],
                dedupe_key=f"schedule:{event.id}:{event.start_time.isoformat()}",
            )
            event.reminded = True
            reminded += 1
            pushed.append((event.user_id, f"⏰ 日程提醒: {event.title}", "/schedule"))
        await db.commit()

    for user_id, title, link in pushed:
        try:
            from plugins.notifications.backend.router import notify_user

            await notify_user(user_id, {
                "type": "new_notification",
                "title": title,
                "link": link,
            })
        except Exception as exc:
            log.warning("schedule reminder push failed for user %s: %s", user_id, exc)
    return {"reminded": reminded}
