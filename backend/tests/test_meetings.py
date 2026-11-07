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


async def test_meeting_job_produces_note(client, monkeypatch):
    token, user_id = await _new_user(client)
    file_id = await _seed_audio(user_id)

    from core.database.session import async_session
    from core.meetings.models import MeetingMinutesJob
    from core.meetings import service as meetings_service

    async with async_session() as db:
        job = MeetingMinutesJob(
            user_id=user_id,
            file_id=file_id,
            title="预算周会",
            status="queued",
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id = job.id

    async def fake_transcribe(file_record, *, diarize=None):
        return {
            "text": "讨论预算。决定周五前完成评审。",
            "segments": [
                {"start": 0, "end": 3, "speaker": "1", "text": "讨论预算"},
                {"start": 3, "end": 7, "speaker": "2", "text": "周五前完成评审"},
            ],
        }

    async def fake_minutes(transcript, bot):
        return {
            "summary": "讨论预算并确定周五前完成评审。",
            "discussion": ["预算方案"],
            "decisions": ["周五前完成评审"],
            "action_items": [{"title": "完成评审", "owner": "张三", "due": "周五"}],
            "risks": [],
        }

    monkeypatch.setattr(meetings_service, "transcribe_minio_object", fake_transcribe)
    monkeypatch.setattr(meetings_service, "_summarise_long", fake_minutes)

    await meetings_service._run_job(job_id)

    async with async_session() as db:
        job = await db.get(MeetingMinutesJob, job_id)
        assert job.status == "done", job.error
        assert job.note_id
        assert job.transcript
        note_id = job.note_id

    r = await client.get(
        f"/api/meetings/minutes/{job_id}",
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "done"
    assert body["minutes"]["action_items"][0]["title"] == "完成评审"

    from plugins.notes.backend.models import PluginNote

    async with async_session() as db:
        note = await db.get(PluginNote, note_id)
        assert note is not None
        assert "预算周会" in note.content

