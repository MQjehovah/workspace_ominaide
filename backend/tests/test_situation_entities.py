"""Situation entity index."""

import random
import string

from conftest import auth


async def _new_user(client):
    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"sitent_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "testpass123",
        },
    )
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["user_id"]
    r = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "testpass123"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"], user_id


async def test_situation_entities_from_event_and_mail(client):
    token, user_id = await _new_user(client)
    from ai.cognition.situation_entities import build_situation_entities
    from ai.entities.service import resolve_entity
    from core.database.session import async_session

    async with async_session() as db:
        await resolve_entity(db, user_id, "person", "张三")
        await resolve_entity(db, user_id, "project", "预算评审")
        await db.commit()

    snapshot = {
        "calendar": [{
            "id": 1,
            "title": "和张三开预算评审会",
            "time": "2026-11-09T10:00:00",
        }],
        "todos": [{"id": 2, "title": "准备预算材料"}],
        "inbox": {"recent_mail": [{"id": 3, "from": "zhangsan@example.com"}]},
        "goals": [{"id": 4, "title": "预算评审"}],
    }
    rows = await build_situation_entities(user_id, snapshot)
    assert any(row["source_type"] == "event" for row in rows)
    assert all(row["entity_id"] for row in rows)
    assert snapshot["entities"] == rows
