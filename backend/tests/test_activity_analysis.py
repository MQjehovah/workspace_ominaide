"""Hourly activity analysis and action execution."""

from datetime import datetime, timedelta

from conftest import auth


async def _new_user(client) -> tuple[str, int]:
    import random
    import string

    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"analysis_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "testpass123"},
    )
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["user_id"]
    r = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "testpass123"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"], user_id


async def test_activity_analysis_produces_cached_suggestions(client):
    token, user_id = await _new_user(client)
    r = await client.post(
        "/api/schedule",
        json={
            "title": "产品评审",
            "start_time": (datetime.now() + timedelta(hours=2)).isoformat(),
        },
        headers=auth(token),
    )
    assert r.status_code in (200, 201), r.text

    from ai.insights.activity_service import analyze_user

    result = await analyze_user(user_id)
    assert result["created"] >= 1

    r = await client.get("/api/proposals", headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["items"]


async def test_execute_suggestion_creates_todo(client):
    token, user_id = await _new_user(client)

    from core.database.session import async_session
    from ai.cognition.models import Proposal

    async with async_session() as db:
        row = Proposal(
            user_id=user_id,
            kind="todo",
            title="准备产品评审",
            reason="会议将至",
            confidence=0.8,
            status="new",
            actions=[{
                "key": "create_todo",
                "label": "执行",
                "kind": "create_todo",
                "payload": {"title": "准备产品评审", "priority": 1},
            }],
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        suggestion_id = row.id

    r = await client.post(
        f"/api/proposals/{suggestion_id}/act",
        json={"action": "execute"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "executed"

    r = await client.get("/api/plugins/todo/items", headers=auth(token))
    assert r.status_code == 200, r.text
    assert any(item["title"] == "准备产品评审" for item in r.json())


async def test_calendar_event_callback_enqueues_job(monkeypatch):
    from activities.models import UserActivity
    from plugins.schedule.backend import external_sync

    calls = []

    async def fake_enqueue(kind, payload, **kwargs):
        calls.append((kind, payload, kwargs))

    monkeypatch.setattr(external_sync, "enqueue", fake_enqueue)
    event = UserActivity(
        id=42,
        user_id=1,
        event_type="calendar.external.upsert",
        details={"provider": "dingtalk", "external_id": "evt-1"},
    )
    await external_sync.on_calendar_event(event)
    assert calls
    assert calls[0][0] == "schedule.external.apply"
    assert calls[0][1] == {"activity_id": 42}


async def test_activity_page_and_distribution_stats(client):
    token, _ = await _new_user(client)
    r = await client.post(
        "/api/activities",
        json={"event_type": "note.created", "summary": "创建笔记", "details": {"title": "周报"}},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        "/api/activities",
        json={"event_type": "todo.created", "summary": "创建待办"},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text

    r = await client.get("/api/activities/page", params={"page": 1, "page_size": 1}, headers=auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1

    r = await client.get("/api/activities/stats", params={"days": 7}, headers=auth(token))
    assert r.status_code == 200, r.text
    stats = r.json()
    assert stats["event_count"] >= 2
    assert "note.created" in stats["type_counts"]
    assert "app_minutes" not in stats
