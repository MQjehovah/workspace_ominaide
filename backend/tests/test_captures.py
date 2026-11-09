"""Quick capture ingestion, analysis and conversion."""

import random
import string

from conftest import auth


async def _new_user(client):
    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"cap_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "testpass123"},
    )
    assert r.status_code in (200, 201), r.text
    uid = r.json()["user_id"]
    r = await client.post("/api/auth/login", json={"username": username, "password": "testpass123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"], uid


async def test_text_capture_analyze_and_convert(client, monkeypatch):
    token, uid = await _new_user(client)

    async def no_enqueue(*args, **kwargs):
        return None

    async def fake_analyze(title, content):
        return {
            "title": "采集标题",
            "summary": "采集摘要",
            "key_points": ["要点一"],
            "tags": ["测试"],
            "people": [],
            "suggested_actions": [{"type": "todo", "title": "跟进"}],
        }

    monkeypatch.setattr("core.jobs.service.enqueue", no_enqueue)
    monkeypatch.setattr("plugins.captures.backend.service._llm_analyze", fake_analyze)

    from plugins.captures.backend.service import analyze_capture, convert_capture, create_capture

    capture = await create_capture(uid, kind="text", text="这是一条随手记")
    result = await analyze_capture(capture.id)
    assert result["status"] == "ready", result

    from plugins.captures.backend.service import get_capture
    row = await get_capture(uid, capture.id)
    assert row.summary == "采集摘要"
    assert row.tags == ["测试"]

    converted = await convert_capture(uid, capture.id, "todo", {"title": "采集待办"})
    assert converted["todo_id"]


async def test_capture_user_scope(client, monkeypatch):
    token_a, uid_a = await _new_user(client)
    token_b, uid_b = await _new_user(client)

    async def no_enqueue(*args, **kwargs):
        return None

    monkeypatch.setattr("core.jobs.service.enqueue", no_enqueue)
    from plugins.captures.backend.service import create_capture, get_capture

    capture = await create_capture(uid_a, kind="text", text="A 的随手记")
    assert await get_capture(uid_b, capture.id) is None
    assert await get_capture(uid_a, capture.id) is not None
