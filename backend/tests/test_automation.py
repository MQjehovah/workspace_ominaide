"""Unified automation: spec compilation, conditions and execution."""

from types import SimpleNamespace


async def _new_user(client):
    import random
    import string

    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"auto_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "testpass123"},
    )
    assert r.status_code in (200, 201), r.text
    uid = r.json()["user_id"]
    r = await client.post("/api/auth/login", json={"username": username, "password": "testpass123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"], uid


def test_compile_spec_compiles_prompt_and_validates_cron():
    from core.automation.dsl import compile_spec

    result = compile_spec({
        "name": "daily",
        "trigger": {"type": "schedule", "cron": "0 9 * * *"},
        "actions": [],
        "prompt": "整理未读",
    })
    assert result["valid"], result
    assert result["spec"]["actions"][0]["type"] == "agent"

    bad = compile_spec({
        "name": "bad",
        "trigger": {"type": "schedule", "cron": "not-a-cron"},
        "actions": [{"type": "notify", "params": {"title": "x"}}],
    })
    assert not bad["valid"]


def test_condition_evaluation():
    from core.automation.dsl import evaluate_conditions

    spec = {
        "match": "all",
        "conditions": [
            {"field": "event.details.important", "op": "eq", "value": True},
            {"field": "event.summary", "op": "contains", "value": "客户"},
        ],
    }
    ok, results = evaluate_conditions(spec, {
        "event": {"details": {"important": True}, "summary": "客户邮件"},
    })
    assert ok and all(item["matched"] for item in results)

    ng, _ = evaluate_conditions(spec, {
        "event": {"details": {"important": False}, "summary": "普通邮件"},
    })
    assert not ng


async def test_manual_automation_executes_actions(client):
    token, uid = await _new_user(client)

    from core.automation.executor import execute_automation
    from core.bots.registry import get_or_create_default_bot
    from core.bots.routines import create_routine

    bot = await get_or_create_default_bot(uid)
    routine = await create_routine(
        uid, bot.id, "auto todo",
        spec={
            "name": "auto todo",
            "trigger": {"type": "manual"},
            "match": "all",
            "conditions": [],
            "actions": [{"type": "todo", "params": {"title": "自动化创建"}}],
        },
    )
    result = await execute_automation(routine.id, "manual", manual={})
    assert result["status"] == "succeeded", result

    from sqlalchemy import select
    from core.database.session import async_session
    from plugins.todo.backend.models import PluginTodoItem

    async with async_session() as db:
        row = (await db.execute(
            select(PluginTodoItem).where(
                PluginTodoItem.user_id == uid,
                PluginTodoItem.title == "自动化创建",
            )
        )).scalar_one_or_none()
    assert row is not None


async def test_event_condition_skips_and_is_idempotent(client):
    _, uid = await _new_user(client)

    from core.automation.executor import execute_automation
    from core.bots.registry import get_or_create_default_bot
    from core.bots.routines import create_routine

    bot = await get_or_create_default_bot(uid)
    routine = await create_routine(
        uid, bot.id, "important mail",
        spec={
            "name": "important mail",
            "trigger": {"type": "event", "event_type": "mail.received"},
            "match": "all",
            "conditions": [
                {"field": "event.details.important", "op": "eq", "value": True},
            ],
            "actions": [{"type": "todo", "params": {"title": "重要邮件跟进"}}],
        },
    )
    event = SimpleNamespace(
        id=90001, event_type="mail.received", summary="普通邮件",
        details={"important": False}, entity_type=None, entity_id=None,
    )
    first = await execute_automation(routine.id, "event", event=event)
    assert first["status"] == "skipped"
    duplicate = await execute_automation(routine.id, "event", event=event)
    assert duplicate["status"] == "skipped" and duplicate.get("reason") == "duplicate"

    event.details = {"important": True}
    event.id = 90002
    ok = await execute_automation(routine.id, "event", event=event)
    assert ok["status"] == "succeeded"
