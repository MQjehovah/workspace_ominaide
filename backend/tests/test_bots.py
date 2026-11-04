from conftest import auth


async def test_default_bot_is_created_lazily(client, user_token):
    r = await client.get("/api/bots", headers=auth(user_token))
    assert r.status_code == 200, r.text
    bots = r.json()
    main = [b for b in bots if b["slug"] == "main"]
    assert len(main) == 1
    assert main[0]["is_default"] is True
    assert main[0]["status"] == "active"


async def test_bot_crud_and_scoping(client, user_token, admin_token):
    r = await client.post(
        "/api/bots",
        json={
            "name": "写作助手",
            "role": "负责选题和初稿",
            "system_prompt": "你是一个写作助手。",
            "model": "test-model",
            "temperature": 0.3,
        },
        headers=auth(user_token),
    )
    assert r.status_code == 200, r.text
    bot = r.json()
    bot_id = bot["id"]
    assert bot["slug"]
    assert bot["model"] == "test-model"
    assert bot["is_default"] is False

    r = await client.get(f"/api/bots/{bot_id}", headers=auth(user_token))
    assert r.status_code == 200
    assert r.json()["name"] == "写作助手"

    # Another user must not see or touch it.
    r = await client.get(f"/api/bots/{bot_id}", headers=auth(admin_token))
    assert r.status_code == 404

    r = await client.patch(
        f"/api/bots/{bot_id}",
        json={"name": "写作 Bot"},
        headers=auth(user_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "写作 Bot"

    r = await client.delete(f"/api/bots/{bot_id}", headers=auth(user_token))
    assert r.status_code == 200
    r = await client.get(f"/api/bots/{bot_id}", headers=auth(user_token))
    assert r.status_code == 404


async def test_default_bot_cannot_be_deleted(client, user_token):
    r = await client.get("/api/bots", headers=auth(user_token))
    main = next(b for b in r.json() if b["is_default"])
    r = await client.delete(f"/api/bots/{main['id']}", headers=auth(user_token))
    assert r.status_code == 409


async def test_bot_memory_crud(client, user_token):
    r = await client.post(
        "/api/bots",
        json={"name": "记忆测试"},
        headers=auth(user_token),
    )
    bot_id = r.json()["id"]

    r = await client.post(
        f"/api/bots/{bot_id}/memories",
        json={"content": "用户偏好先列大纲再写正文", "kind": "preference"},
        headers=auth(user_token),
    )
    assert r.status_code == 200, r.text
    memory = r.json()
    assert memory["kind"] == "preference"

    r = await client.get(
        f"/api/bots/{bot_id}/memories", headers=auth(user_token)
    )
    assert r.status_code == 200
    assert any(m["id"] == memory["id"] for m in r.json())

    r = await client.delete(
        f"/api/bots/{bot_id}/memories/{memory['id']}", headers=auth(user_token)
    )
    assert r.status_code == 200
    r = await client.get(
        f"/api/bots/{bot_id}/memories", headers=auth(user_token)
    )
    assert all(m["id"] != memory["id"] for m in r.json())


async def test_memory_context_is_bot_scoped(client, user_token):
    me = (await client.get("/api/auth/me", headers=auth(user_token))).json()
    uid = me["id"]

    a = (
        await client.post(
            "/api/bots", json={"name": "记忆 A"}, headers=auth(user_token)
        )
    ).json()
    b = (
        await client.post(
            "/api/bots", json={"name": "记忆 B"}, headers=auth(user_token)
        )
    ).json()

    r = await client.post(
        f"/api/bots/{a['id']}/memories",
        json={"content": "A 的私有事实：喜欢深色主题"},
        headers=auth(user_token),
    )
    assert r.status_code == 200, r.text

    from core.bots.memory import build_bot_context
    from core.bots.registry import get_active_bot

    bot_a = await get_active_bot(uid, a["id"])
    bot_b = await get_active_bot(uid, b["id"])
    ctx_a = await build_bot_context(uid, bot_a, "")
    ctx_b = await build_bot_context(uid, bot_b, "")

    assert "喜欢深色主题" in (ctx_a or "")
    assert "喜欢深色主题" not in (ctx_b or "")


async def test_switching_default_bot(client, user_token):
    me = (await client.get("/api/auth/me", headers=auth(user_token))).json()
    uid = me["id"]

    c = (
        await client.post(
            "/api/bots",
            json={"name": "默认 Bot C", "is_default": True},
            headers=auth(user_token),
        )
    ).json()

    from core.bots.registry import get_active_bot

    active = await get_active_bot(uid, None)
    assert active.id == c["id"]

    d = (
        await client.post(
            "/api/bots",
            json={"name": "默认 Bot D", "is_default": True},
            headers=auth(user_token),
        )
    ).json()

    bots = (await client.get("/api/bots", headers=auth(user_token))).json()
    defaults = [b for b in bots if b["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["id"] == d["id"]


async def test_policy_classification_and_decisions():
    from core.bots.policy import classify_tool, decide

    assert classify_tool("search_files") == "read"
    assert classify_tool("create_schedule_event") == "write"
    assert classify_tool("shell.exec") == "exec"
    assert classify_tool("send_email") == "external"

    assert decide(None, "search_files")[1] == "auto"
    assert decide(None, "create_schedule_event")[1] == "auto"
    assert decide(None, "shell.exec")[1] == "ask"
    assert decide(None, "send_email")[1] == "ask"

    class Bot:
        risk_policy = {"tools": {"shell.exec": "deny", "search_files": "ask"}}

    assert decide(Bot(), "shell.exec") == ("exec", "deny")
    assert decide(Bot(), "search_files") == ("read", "ask")


async def test_cron_next_run():
    from datetime import datetime
    from core.bots.routines import cron_matches, next_run

    base = datetime(2026, 11, 4, 7, 29)
    assert next_run("30 7 * * *", base) == datetime(2026, 11, 4, 7, 30)
    assert cron_matches("30 7 * * *", datetime(2026, 11, 4, 7, 30))
    assert not cron_matches("30 7 * * *", datetime(2026, 11, 4, 7, 31))
    assert next_run("*/15 * * * *", datetime(2026, 11, 4, 7, 31)) == datetime(
        2026, 11, 4, 7, 45
    )


async def test_run_lifecycle_and_cancel(client, user_token):
    bots = (await client.get("/api/bots", headers=auth(user_token))).json()
    bot_id = next(b for b in bots if b["is_default"])["id"]

    r = await client.post(
        f"/api/bots/{bot_id}/runs",
        json={"prompt": "整理一下今天的待办", "auto_start": False},
        headers=auth(user_token),
    )
    assert r.status_code == 202, r.text
    run = r.json()
    assert run["status"] == "queued"
    run_id = run["id"]

    r = await client.get(f"/api/runs/{run_id}", headers=auth(user_token))
    assert r.status_code == 200
    assert r.json()["status"] == "queued"

    r = await client.post(f"/api/runs/{run_id}/cancel", headers=auth(user_token))
    assert r.status_code == 200

    r = await client.get(f"/api/runs/{run_id}", headers=auth(user_token))
    assert r.json()["status"] == "cancelled"

    r = await client.get(f"/api/runs/{run_id}/stream", headers=auth(user_token))
    assert r.status_code == 200
    assert '"type": "done"' in r.text
    assert "cancelled" in r.text


async def test_routine_crud_and_seed(client, user_token):
    bots = (await client.get("/api/bots", headers=auth(user_token))).json()
    bot_id = next(b for b in bots if b["is_default"])["id"]

    r = await client.post(
        f"/api/bots/{bot_id}/routines",
        json={
            "name": "日报",
            "trigger_type": "cron",
            "cron_expr": "0 22 * * *",
            "prompt": "汇总今天的未读 RSS",
        },
        headers=auth(user_token),
    )
    assert r.status_code == 200, r.text
    routine = r.json()
    assert routine["next_run_at"] is not None

    r = await client.patch(
        f"/api/bots/{bot_id}/routines/{routine['id']}",
        json={"enabled": False},
        headers=auth(user_token),
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is False

    r = await client.post(
        f"/api/bots/{bot_id}/routines",
        json={"name": "坏 cron", "trigger_type": "cron", "cron_expr": "bad"},
        headers=auth(user_token),
    )
    assert r.status_code == 422

    # Seed is idempotent and creates the morning briefing routine.
    from core.bots import routines as routine_service
    from core.bots.routines import seed_default_routines

    await seed_default_routines()
    await seed_default_routines()
    me = (await client.get("/api/auth/me", headers=auth(user_token))).json()
    all_routines = await routine_service.list_routines(me["id"])
    morning = [x for x in all_routines if x.name == "morning_brief"]
    assert len(morning) == 1

    r = await client.delete(
        f"/api/bots/{bot_id}/routines/{routine['id']}", headers=auth(user_token)
    )
    assert r.status_code == 200


async def test_save_memory_tool_uses_bot_scope(client, user_token):
    me = (await client.get("/api/auth/me", headers=auth(user_token))).json()
    uid = me["id"]
    bots = (await client.get("/api/bots", headers=auth(user_token))).json()
    bot_id = next(b for b in bots if b["is_default"])["id"]

    from core.ai.mcp.tools.knowledge import save_memory
    from core.bots.context import reset_current_bot_id, set_current_bot_id
    from core.bots.registry import get_active_bot

    bot = await get_active_bot(uid, bot_id)
    token = set_current_bot_id(bot.id)
    try:
        result = await save_memory(uid, {"fact": "工具记忆测试：喜欢深色模式"})
    finally:
        reset_current_bot_id(token)

    assert not result.isError, result
    memories = (
        await client.get(f"/api/bots/{bot_id}/memories", headers=auth(user_token))
    ).json()
    assert any("深色模式" in m["content"] for m in memories)


async def test_approvals_list_and_validation(client, user_token):
    r = await client.get("/api/approvals?status=pending", headers=auth(user_token))
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    r = await client.post(
        "/api/approvals/999999/decision",
        json={"approved": True},
        headers=auth(user_token),
    )
    assert r.status_code == 404


async def test_run_approval_state_machine(client, user_token, monkeypatch):
    """A risky tool pauses the run; approving resumes and finishes it."""
    from core.ai.mcp.core import MCPCallResponse, MCPContent, MCPTool
    from core.ai.mcp.registry import tool_registry
    from core.bots import runner
    from core.config.settings import settings

    async def fake_tool(user_id, args):
        return MCPCallResponse(content=[MCPContent(text="tool executed")])

    tool_registry.register(
        MCPTool(
            name="shell.exec",
            description="fake exec tool for tests",
            inputSchema={"type": "object", "properties": {}},
        ),
        fake_tool,
    )

    calls = {"n": 0}

    async def fake_stream(client_, run_id, bot, messages, tools):
        calls["n"] += 1
        if calls["n"] == 1:
            return "", "", [
                {"id": "call_1", "name": "shell.exec", "arguments": {"cmd": "echo hi"}}
            ]
        return "approved and done", "", []

    monkeypatch.setattr(runner, "_stream_completion", fake_stream)
    monkeypatch.setattr(runner, "enqueue_run", lambda run_id: None)
    monkeypatch.setattr(settings, "bot_run_auto_summary", False)

    bots = (await client.get("/api/bots", headers=auth(user_token))).json()
    bot_id = next(b for b in bots if b["is_default"])["id"]

    r = await client.post(
        f"/api/bots/{bot_id}/runs",
        json={"prompt": "run a shell command", "auto_start": False},
        headers=auth(user_token),
    )
    run_id = r.json()["id"]

    await runner.execute_run(run_id)
    r = await client.get(f"/api/runs/{run_id}", headers=auth(user_token))
    assert r.json()["status"] == "waiting_approval", r.text

    approvals = (
        await client.get("/api/approvals?status=pending", headers=auth(user_token))
    ).json()
    approval = next(a for a in approvals if a["run_id"] == run_id)
    assert approval["risk_level"] == "exec"

    r = await client.post(
        f"/api/approvals/{approval['id']}/decision",
        json={"approved": True},
        headers=auth(user_token),
    )
    assert r.status_code == 200

    await runner.execute_run(run_id)
    r = await client.get(f"/api/runs/{run_id}", headers=auth(user_token))
    body = r.json()
    assert body["status"] == "done", body
    assert body["output"] == "approved and done"
    assert any(s["tool_name"] == "shell.exec" for s in body["steps"])

    tool_registry._tools.pop("shell.exec", None)
