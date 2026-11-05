"""Actionable notifications + todo deadline reminders."""
from datetime import datetime, timedelta

from conftest import auth


async def _new_user(client) -> tuple[str, int]:
    import random
    import string

    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"notif_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "testpass123"},
    )
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["user_id"]
    r = await client.post("/api/auth/login", json={"username": username, "password": "testpass123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"], user_id


async def _create_todo(client, token: str, title: str, due: datetime | None = None) -> int:
    r = await client.post(
        "/api/plugins/todo/items",
        json={"title": title, "due_date": due.isoformat() if due else None},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _create_notification(user_id: int, actions: list, title: str = "测试通知", type_: str = "info") -> int:
    from core.database.session import async_session
    from plugins.notifications.backend.service import create_notification

    async with async_session() as db:
        n = await create_notification(
            db, user_id, title, "正文", type_, None, actions=actions,
            dedupe_key=f"test:{user_id}:{title}",
        )
        await db.commit()
        return n.id


async def test_notification_complete_todo_action(client):
    token, user_id = await _new_user(client)
    todo_id = await _create_todo(client, token, "提交周报")
    nid = await _create_notification(user_id, [
        {"key": "complete", "label": "完成", "kind": "complete_todo", "todo_id": todo_id},
    ])

    r = await client.post(
        f"/api/notifications/{nid}/action", json={"action": "complete"}, headers=auth(token)
    )
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/plugins/todo/items/{todo_id}", headers=auth(token))
    assert r.json()["status"] == "done"

    r = await client.get("/api/notifications", headers=auth(token))
    row = next(x for x in r.json() if x["id"] == nid)
    assert row["read"] is True
    assert row["actions"][0]["kind"] == "complete_todo"


async def test_notification_snooze_hides_until_due(client):
    token, user_id = await _new_user(client)
    nid = await _create_notification(user_id, [
        {"key": "later", "label": "稍后", "kind": "snooze", "minutes": 10},
    ], title="稍后提醒我")

    r = await client.post(
        f"/api/notifications/{nid}/action", json={"action": "later"}, headers=auth(token)
    )
    assert r.status_code == 200, r.text
    assert "scheduled_at" in r.json()

    r = await client.get("/api/notifications", headers=auth(token))
    assert all(x["id"] != nid for x in r.json())
    r = await client.get("/api/notifications/unread-count", headers=auth(token))
    assert r.json()["count"] == 0


async def test_notification_actions_are_user_scoped(client):
    token_a, user_a = await _new_user(client)
    token_b, _ = await _new_user(client)
    nid = await _create_notification(user_a, [
        {"key": "open", "label": "打开", "kind": "open", "link": "/notes"},
    ])

    r = await client.post(
        f"/api/notifications/{nid}/action", json={"action": "open"}, headers=auth(token_b)
    )
    assert r.status_code == 404
    r = await client.delete(f"/api/notifications/{nid}", headers=auth(token_b))
    assert r.status_code == 404

    r = await client.post(
        f"/api/notifications/{nid}/action", json={"action": "open"}, headers=auth(token_a)
    )
    assert r.status_code == 200
    assert r.json()["link"] == "/notes"


async def test_todo_deadline_creates_actionable_reminder_once(client):
    from core.ai.scheduler import _check_reminders
    from core.database.session import async_session
    from plugins.notifications.backend.models import Notification
    from sqlalchemy import select

    token, user_id = await _new_user(client)
    due = datetime.now() + timedelta(minutes=10)
    todo_id = await _create_todo(client, token, "交房租", due)

    await _check_reminders()
    async with async_session() as db:
        rows = list((await db.execute(
            select(Notification).where(
                Notification.user_id == user_id,
                Notification.type == "todo_reminder",
            )
        )).scalars().all())
    assert len(rows) == 1
    assert "交房租" in rows[0].title
    assert any(a.get("kind") == "complete_todo" for a in rows[0].actions)

    # Reminded todos are not reminded again.
    await _check_reminders()
    async with async_session() as db:
        count = len(list((await db.execute(
            select(Notification).where(
                Notification.user_id == user_id,
                Notification.type == "todo_reminder",
            )
        )).scalars().all()))
    assert count == 1


async def test_rescheduling_event_resets_reminded(client):
    from core.database.session import async_session
    from plugins.schedule.backend.models import Event

    token, user_id = await _new_user(client)
    r = await client.post(
        "/api/schedule",
        json={
            "title": "评审会",
            "start_time": (datetime.now() + timedelta(hours=2)).isoformat(),
            "remind_before": 30,
        },
        headers=auth(token),
    )
    assert r.status_code in (200, 201), r.text
    event_id = r.json()["id"]

    async with async_session() as db:
        ev = await db.get(Event, event_id)
        ev.reminded = True
        await db.commit()

    r = await client.put(
        f"/api/schedule/{event_id}",
        json={"start_time": (datetime.now() + timedelta(hours=5)).isoformat()},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text

    async with async_session() as db:
        ev = await db.get(Event, event_id)
        assert ev.reminded is False


async def test_todo_due_date_change_resets_reminded(client):
    from core.database.session import async_session
    from plugins.todo.backend.models import PluginTodoItem

    token, _ = await _new_user(client)
    todo_id = await _create_todo(client, token, "续费域名", datetime.now() + timedelta(days=1))

    async with async_session() as db:
        todo = await db.get(PluginTodoItem, todo_id)
        todo.reminded = True
        await db.commit()

    r = await client.put(
        f"/api/plugins/todo/items/{todo_id}",
        json={"due_date": (datetime.now() + timedelta(days=2)).isoformat()},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    async with async_session() as db:
        todo = await db.get(PluginTodoItem, todo_id)
        assert todo.reminded is False
