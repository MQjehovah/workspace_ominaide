"""Meeting minutes job API: MinIO file reference, retention and deletion."""

import random
import string

from conftest import auth


async def _new_user(client):
    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"minutes_{suffix}"
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


async def _seed_audio(user_id: int) -> int:
    from core.database.session import async_session
    from plugins.files.backend.models import File

    async with async_session() as db:
        record = File(
            user_id=user_id,
            bucket="user-files",
            object_key=f"{user_id}/meeting.m4a",
            original_name="周会录音.m4a",
            size=1024,
            mime_type="audio/mp4",
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record.id


async def test_create_list_and_delete_meeting_minutes(client, monkeypatch):
    token, user_id = await _new_user(client)
    file_id = await _seed_audio(user_id)

    from core.meetings import router as meetings_router

    scheduled: list[int] = []
    monkeypatch.setattr(meetings_router, "schedule_job", scheduled.append)

    r = await client.post(
        "/api/meetings/minutes",
        json={"file_id": file_id, "title": "周会纪要"},
        headers=auth(token),
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "queued"
    assert body["file_id"] == file_id
    assert body["title"] == "周会纪要"
    assert scheduled == [body["id"]]

    r = await client.get("/api/meetings/minutes", headers=auth(token))
    assert r.status_code == 200, r.text
    assert [item["id"] for item in r.json()["items"]] == [body["id"]]

    # Audio is retained by default.
    from core.database.session import async_session
    from plugins.files.backend.models import File

    async with async_session() as db:
        assert await db.get(File, file_id) is not None

    r = await client.delete(
        f"/api/meetings/minutes/{body['id']}?delete_audio=true",
        headers=auth(token),
    )
    assert r.status_code == 200, r.text

    async with async_session() as db:
        assert await db.get(File, file_id) is None


async def test_meeting_minutes_requires_auth(client):
    assert (await client.get("/api/meetings/minutes")).status_code == 401
