from datetime import datetime, timedelta

from conftest import auth


async def _me(client, token):
    return (await client.get("/api/auth/me", headers=auth(token))).json()


async def test_todo_event_note_management_tools(client, user_token):
    me = await _me(client, user_token)
    uid = me["id"]

    from core.database.session import async_session
    from plugins.notes.backend.schemas import NoteCreate
    from plugins.notes.backend.service import create_note
    from plugins.schedule.backend.schemas import EventCreate
    from plugins.schedule.backend.service import create_event
    from plugins.todo.backend.schemas import TodoCreate
    from plugins.todo.backend.service import create_todo

    async with async_session() as db:
        todo = await create_todo(db, uid, TodoCreate(title="管理工具测试"))
        note = await create_note(db, uid, NoteCreate(title="旧标题", content="旧正文"))
        event = await create_event(
            db,
            uid,
            EventCreate(
                title="旧日程",
                start_time=datetime.now() + timedelta(hours=1),
            ),
        )
        await db.commit()
        await db.refresh(todo)
        await db.refresh(note)
        await db.refresh(event)
        todo_id, note_id, event_id = todo.id, note.id, event.id

    from core.ai.mcp.tools import management

    result = await management.todo_update(uid, {"todo_id": todo_id, "title": "新待办"})
    assert not result.isError
    result = await management.todo_complete(uid, {"todo_id": todo_id})
    assert not result.isError and "done" in result.content[0].text
    result = await management.todo_delete(uid, {"todo_id": todo_id})
    assert not result.isError

    result = await management.note_update(uid, {"note_id": note_id, "title": "新标题", "content": "新正文"})
    assert not result.isError
    result = await management.note_delete(uid, {"note_id": note_id})
    assert not result.isError

    result = await management.event_update(uid, {"event_id": event_id, "title": "新日程"})
    assert not result.isError
    result = await management.event_delete(uid, {"event_id": event_id})
    assert not result.isError


async def test_memory_routine_and_project_tools(client, user_token, tmp_path, monkeypatch):
    me = await _me(client, user_token)
    uid = me["id"]
    bots = (await client.get("/api/bots", headers=auth(user_token))).json()
    bot_id = next(b for b in bots if b["is_default"])["id"]

    from core.bots.context import reset_current_bot_id, set_current_bot_id
    from core.bots.memory import add_memory
    from core.ai.mcp.tools import management

    mem = await add_memory(uid, bot_id, "测试记忆：喜欢深色模式")
    token = set_current_bot_id(bot_id)
    try:
        result = await management.memory_list(uid, {"limit": 20})
        assert not result.isError and "深色模式" in result.content[0].text
        result = await management.memory_delete(uid, {"memory_id": mem.id})
        assert not result.isError

        result = await management.routine_create(
            uid,
            {"name": "测试例程", "trigger_type": "cron", "cron_expr": "0 7 * * *"},
        )
        assert not result.isError, result.content[0].text
        routine_id = int(result.content[0].text.split("#")[1].split("：")[0])
        result = await management.routine_list(uid, {})
        assert not result.isError and "测试例程" in result.content[0].text
        result = await management.routine_delete(uid, {"routine_id": routine_id})
        assert not result.isError
    finally:
        reset_current_bot_id(token)

    from core.config.settings import settings

    monkeypatch.setattr(settings, "coding_workspace_root", str(tmp_path))
    project_dir = tmp_path / "managed"
    project_dir.mkdir()
    result = await management.project_create(
        uid,
        {"name": "managed", "path": str(project_dir), "is_git": False},
    )
    assert not result.isError, result.content[0].text
    project_id = int(result.content[0].text.split("#")[1].split("：")[0])
    result = await management.project_update(uid, {"project_id": project_id, "name": "managed2"})
    assert not result.isError
    result = await management.project_delete(uid, {"project_id": project_id})
    assert not result.isError
    assert not project_dir.exists()


async def test_run_shell_tool(tmp_path, monkeypatch):
    from core.config.settings import settings
    from core.ai.mcp.tools.system import run_shell

    monkeypatch.setattr(settings, "shell_default_cwd", str(tmp_path))
    monkeypatch.setattr(settings, "coding_workspace_root", str(tmp_path))
    result = await run_shell(1, {"command": "echo shell-ok", "cwd": str(tmp_path)})
    assert not result.isError, result.content[0].text
    assert "shell-ok" in result.content[0].text


def test_risky_tools_require_approval():
    from core.bots.policy import classify_tool, decide

    assert classify_tool("ha_toggle") == "external"
    assert classify_tool("send_email") == "external"
    assert classify_tool("run_shell") == "exec"
    assert classify_tool("file_delete") == "dangerous"
    assert classify_tool("event_delete") == "dangerous"
    assert decide(None, "ha_toggle")[1] == "ask"
    assert decide(None, "file_delete")[1] == "ask"
    assert decide(None, "search_files")[1] == "auto"
