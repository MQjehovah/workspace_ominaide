"""Capabilities: persistent jobs, graph/context and cursor pagination."""

import asyncio
import random
import string

from conftest import auth


async def _new_user(client):
    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"cap_{suffix}"
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


async def test_background_job_lifecycle(client):
    token, _ = await _new_user(client)
    from core.jobs import service as jobs

    seen: list[int] = []

    async def handler(job):
        seen.append(job.id)

    jobs.register_handler("test.noop", handler)
    # conftest disables the app's background workers so other tests stay
    # deterministic; this test owns one worker explicitly.
    jobs.start_workers(1)
    try:
        r = await client.post(
            "/api/jobs",
            json={"kind": "test.noop", "payload": {"x": 1}},
            headers=auth(token),
        )
        assert r.status_code == 200, r.text
        job_id = r.json()["id"]

        for _ in range(100):
            await asyncio.sleep(0.1)
            r = await client.get("/api/jobs", headers=auth(token))
            row = next(item for item in r.json()["items"] if item["id"] == job_id)
            if row["status"] in {"done", "failed", "dead"}:
                break
        assert row["status"] == "done", row
        assert job_id in seen
    finally:
        await jobs.stop_workers()


async def test_graph_context(client):
    token, user_id = await _new_user(client)

    from core.database.session import async_session
    from plugins.notes.backend.models import PluginNote

    async with async_session() as db:
        note = PluginNote(
            user_id=user_id,
            title="客户跟进记录",
            content="客户说下周一确认预算",
            is_folder=0,
        )
        db.add(note)
        await db.commit()
        await db.refresh(note)
        note_id = note.id

    r = await client.post(
        "/api/graph/links",
        json={
            "from_type": "note",
            "from_id": note_id,
            "to_type": "todo",
            "to_id": 999,
            "relation": "source_of",
        },
        headers=auth(token),
    )
    assert r.status_code == 200, r.text

    r = await client.get(
        f"/api/graph/related?type=note&id={note_id}",
        headers=auth(token),
    )
    assert r.status_code == 200, r.text

    r = await client.get(
        "/api/context/build?q=客户",
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] >= 1
    assert body["items"][0]["citation"].startswith("note:")

async def test_cursor_pagination_helpers():
    from core.pagination import decode_int_cursor, encode_cursor

    cursor = encode_cursor(42)
    assert decode_int_cursor(cursor) == 42
    assert decode_int_cursor("not-a-cursor") is None
