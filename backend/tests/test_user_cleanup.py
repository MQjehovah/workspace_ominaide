"""User deletion and cleanup behavior."""

import random
import string
from datetime import datetime, date

from conftest import auth


async def _new_user(client):
    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"del_{suffix}"
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
    return r.json()["access_token"], user_id, username


def _use_tmp_workspace(tmp_path, monkeypatch):
    from core.config.settings import settings

    monkeypatch.setattr(settings, "workspace_root", str(tmp_path))
    monkeypatch.setattr(settings, "coding_workspace_root", "")


class _FakeMinio:
    def __init__(self):
        self.removed = []

    def list_objects(self, bucket, prefix="", recursive=True):
        return iter([])

    def remove_object(self, bucket, key):
        self.removed.append((bucket, key))


async def _seed_user_data(user_id: int) -> None:
    from ai.insights.review_models import DailyInsight
    from ai.automation.models import AutomationRun
    from ai.bots.models import (
        Bot, BotApproval, BotMemory, BotRoutine, BotRun, BotRunStep,
    )
    from ai.coding.models import CodingRun
    from ai.skills.models import BotSkill
    from core.database.session import async_session
    from activities.models import UserActivity
    from core.jobs.models import BackgroundJob
    from ai.mcp_hub.models import McpServer, McpTool
    from app.objects.models import BusinessComment
    from core.observability.models import RequestTrace
    from plugins.files.backend.models import File
    from plugins.music.backend.models import Playlist, PlaylistItem
    from plugins.notes.backend.models import PluginNote
    from plugins.notifications.backend.models import Notification
    from plugins.projects.backend.models import Project
    from plugins.schedule.backend.models import Event
    from plugins.sources.backend.models import ContentItem, ContentSource
    from plugins.files.backend.sync_models import SyncEvent, SyncFolder
    from plugins.todo.backend.models import PluginTodoItem

    async with async_session() as db:
        bot = Bot(user_id=user_id, slug="main", name="main")
        db.add(bot)
        await db.flush()

        run = BotRun(bot_id=bot.id, user_id=user_id, status="done", input="hello")
        db.add(run)
        await db.flush()
        db.add(BotRunStep(run_id=run.id, seq=1, type="tool", tool_name="x"))
        db.add(BotMemory(bot_id=bot.id, user_id=user_id, content="m"))
        db.add(BotSkill(bot_id=bot.id, user_id=user_id, skill_key="daily-brief"))
        db.add(BotApproval(
            run_id=run.id, bot_id=bot.id, user_id=user_id,
            tool_name="local_shell", risk_level="exec",
        ))
        routine = BotRoutine(bot_id=bot.id, user_id=user_id, name="r")
        db.add(routine)
        await db.flush()
        db.add(AutomationRun(
            routine_id=routine.id, user_id=user_id, trigger_type="manual",
            status="done", idempotency_key=f"test-{user_id}",
        ))
        db.add(CodingRun(run_id=run.id, user_id=user_id, project_path="/tmp/x"))

        server = McpServer(
            user_id=user_id, slug=f"dingtalk-{user_id}", name="钉钉",
            transport="http", url="http://example.invalid/mcp",
        )
        db.add(server)
        await db.flush()
        db.add(McpTool(server_id=server.id, name="tool"))

        file_row = File(
            user_id=user_id, bucket="user-files", object_key=f"{user_id}/a.txt",
            original_name="a.txt", size=3, status="active",
        )
        db.add(file_row)
        await db.flush()
        playlist = Playlist(user_id=user_id, name="list")
        db.add(playlist)
        await db.flush()
        db.add(PlaylistItem(playlist_id=playlist.id, file_id=file_row.id))

        source = ContentSource(user_id=user_id, url="https://example.com/feed")
        db.add(source)
        await db.flush()
        db.add(ContentItem(source_id=source.id, guid="g1", title="item"))

        folder = SyncFolder(user_id=user_id, local_path="/tmp/sync")
        db.add(folder)
        await db.flush()
        db.add(SyncEvent(
            user_id=user_id, sync_folder_id=folder.id, event_type="created",
            file_id=file_row.id, file_path="/a.txt",
        ))

        db.add(Project(user_id=user_id, name="p", path="/tmp/p", is_git=False))
        db.add(PluginNote(user_id=user_id, title="note"))
        db.add(PluginTodoItem(user_id=user_id, title="todo"))
        db.add(Event(user_id=user_id, title="event", start_time=datetime.now()))
        db.add(BackgroundJob(user_id=user_id, kind="test.cleanup", status="queued"))
        db.add(UserActivity(user_id=user_id, event_type="test"))
        db.add(RequestTrace(
            trace_id=f"trace-{user_id}", user_id=user_id, kind="request",
            name="cleanup", status="ok", duration_ms=1,
        ))
        db.add(DailyInsight(user_id=user_id, day=date.today(), summary="s"))
        db.add(Notification(user_id=user_id, title="n"))
        db.add(BusinessComment(
            user_id=user_id, object_type="note", object_id=1, content="c",
        ))
        await db.commit()


async def test_delete_user_data_cleans_everything(client, tmp_path, monkeypatch):
    _use_tmp_workspace(tmp_path, monkeypatch)
    _, user_id, _ = await _new_user(client)

    from core.paths import ensure_user_workspace, user_root

    ensure_user_workspace(user_id)
    (user_root(user_id) / "projects" / "leftover.txt").write_text("x")

    await _seed_user_data(user_id)

    from sqlalchemy import text

    from core.database.session import engine

    other_user = user_id + 100000
    async with engine.begin() as conn:
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS embeddings ("
            "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, content TEXT)"
        ))
        await conn.execute(
            text("INSERT INTO embeddings (user_id, content) VALUES (:uid, :text)"),
            {"uid": user_id, "text": "target"},
        )
        await conn.execute(
            text("INSERT INTO embeddings (user_id, content) VALUES (:uid, :text)"),
            {"uid": other_user, "text": "keep"},
        )

    fake = _FakeMinio()
    monkeypatch.setattr("core.minio.client.minio_client", fake)

    from core.auth.domain.cleanup import delete_user_data

    result = await delete_user_data(user_id)
    assert result["found"] is True
    assert result["workspace_deleted"] is True
    assert result["embeddings_deleted"] == 1
    assert not user_root(user_id).exists()
    assert ("user-files", f"{user_id}/a.txt") in fake.removed

    from sqlalchemy import select

    from ai.insights.review_models import DailyInsight
    from core.auth.domain.models import User
    from ai.automation.models import AutomationRun
    from ai.bots.models import (
        Bot, BotApproval, BotMemory, BotRoutine, BotRun, BotRunStep,
    )
    from ai.coding.models import CodingRun
    from ai.skills.models import BotSkill
    from core.database.session import async_session
    from activities.models import UserActivity
    from core.jobs.models import BackgroundJob
    from ai.mcp_hub.models import McpServer, McpTool
    from core.observability.models import RequestTrace
    from plugins.files.backend.models import File
    from plugins.music.backend.models import Playlist, PlaylistItem
    from plugins.notes.backend.models import PluginNote
    from plugins.notifications.backend.models import Notification
    from plugins.projects.backend.models import Project
    from plugins.schedule.backend.models import Event
    from plugins.sources.backend.models import ContentItem, ContentSource
    from plugins.files.backend.sync_models import SyncEvent, SyncFolder
    from plugins.todo.backend.models import PluginTodoItem

    async with async_session() as db:
        assert (await db.execute(
            select(User.id).where(User.id == user_id)
        )).scalar_one_or_none() is None
        for model in (
            Bot, BotApproval, BotMemory, BotRoutine, BotRun, BotRunStep,
            BotSkill, AutomationRun, CodingRun, McpServer, McpTool,
            File, Playlist, PlaylistItem, ContentSource, ContentItem,
            SyncFolder, SyncEvent, Project, PluginNote, PluginTodoItem,
            Event, BackgroundJob, UserActivity, RequestTrace,
            DailyInsight, Notification,
        ):
            if hasattr(model, "user_id"):
                count = (await db.execute(
                    select(model).where(model.user_id == user_id)
                )).scalars().all()
            elif model is BotRunStep:
                run_ids = (await db.execute(
                    select(BotRun.id).where(BotRun.user_id == user_id)
                )).scalars().all()
                count = (await db.execute(
                    select(model).where(model.run_id.in_(run_ids or [0]))
                )).scalars().all()
            elif model is McpTool:
                server_ids = (await db.execute(
                    select(McpServer.id).where(McpServer.user_id == user_id)
                )).scalars().all()
                count = (await db.execute(
                    select(model).where(model.server_id.in_(server_ids or [0]))
                )).scalars().all()
            else:
                count = []
            assert count == [], f"leftover rows in {model.__tablename__}"

    async with engine.begin() as conn:
        target_rows = (await conn.execute(
            text("SELECT count(*) FROM embeddings WHERE user_id = :uid"),
            {"uid": user_id},
        )).scalar()
        kept_rows = (await conn.execute(
            text("SELECT count(*) FROM embeddings WHERE user_id = :uid"),
            {"uid": other_user},
        )).scalar()
    assert target_rows == 0
    assert kept_rows == 1

    # Second call is idempotent.
    again = await delete_user_data(user_id)
    assert again["already_deleted"] is True


async def test_delete_api_requires_confirm_and_enqueues(client, admin_token, tmp_path, monkeypatch):
    _use_tmp_workspace(tmp_path, monkeypatch)
    _, target_id, target_name = await _new_user(client)
    admin_me = (await client.get("/api/auth/me", headers=auth(admin_token))).json()

    r = await client.delete(
        f"/api/auth/users/{target_id}", headers=auth(admin_token)
    )
    assert r.status_code == 400

    r = await client.delete(
        f"/api/auth/users/{target_id}",
        params={"confirm": "wrong-name"},
        headers=auth(admin_token),
    )
    assert r.status_code == 400

    r = await client.delete(
        f"/api/auth/users/{target_id}",
        params={"confirm": target_name},
        headers=auth(admin_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["job_id"]

    # Self deletion is always rejected, even with the right username.
    r = await client.delete(
        f"/api/auth/users/{admin_me['id']}",
        params={"confirm": admin_me["username"]},
        headers=auth(admin_token),
    )
    assert r.status_code == 400
