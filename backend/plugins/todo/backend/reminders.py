"""Todo deadline reminder checks owned by the todo plugin."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from core.database.session import async_session
from core.logging import get_logger
from plugins.notifications.backend.service import create_notification
from plugins.todo.backend.models import PluginTodoItem

log = get_logger(__name__)


async def check_todo_reminders() -> dict:
    now = datetime.now()
    window = now + timedelta(minutes=30)
    floor = now - timedelta(hours=24)
    reminded = 0
    async with async_session() as db:
        rows = list((await db.execute(
            select(PluginTodoItem).where(
                PluginTodoItem.status != "done",
                PluginTodoItem.reminded == False,  # noqa: E712
                PluginTodoItem.due_date != None,  # noqa: E711
                PluginTodoItem.due_date <= window,
                PluginTodoItem.due_date >= floor,
            )
        )).scalars().all())

        pushed: list[tuple[int, str, str]] = []
        for todo in rows:
            await create_notification(
                db,
                todo.user_id,
                f"⏳ 待办提醒: {todo.title}",
                f"截止 {todo.due_date.strftime('%m-%d %H:%M')}",
                "todo_reminder",
                "/apps/todo",
                actions=[
                    {
                        "key": "complete",
                        "label": "标记完成",
                        "kind": "complete_todo",
                        "todo_id": todo.id,
                    },
                    {
                        "key": "snooze",
                        "label": "10 分钟后",
                        "kind": "snooze",
                        "minutes": 10,
                    },
                ],
                dedupe_key=f"todo:{todo.id}:{todo.due_date.isoformat()}",
            )
            todo.reminded = True
            reminded += 1
            pushed.append((todo.user_id, f"⏳ 待办提醒: {todo.title}", "/apps/todo"))
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
            log.warning("todo reminder push failed for user %s: %s", user_id, exc)
    return {"reminded": reminded}
