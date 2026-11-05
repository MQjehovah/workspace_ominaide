"""Automation center: templates, natural-language parsing, dry runs and logs."""
from datetime import datetime

from conftest import auth


async def _new_user(client) -> tuple[str, int]:
    import random
    import string

    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"auto_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "testpass123"},
    )
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["user_id"]
    r = await client.post("/api/auth/login", json={"username": username, "password": "testpass123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"], user_id


async def _default_bot(client, token: str) -> int:
    r = await client.get("/api/bots", headers=auth(token))
    assert r.status_code == 200, r.text
    return next(b for b in r.json() if b["is_default"])["id"]


async def _create_routine(client, token: str, bot_id: int, **overrides) -> dict:
    payload = {
        "name": "测试例程",
        "trigger_type": "cron",
        "cron_expr": "0 9 * * *",
        "prompt": "总结今天的日程",
        "enabled": True,
        **overrides,
    }
    r = await client.post(f"/api/bots/{bot_id}/routines", json=payload, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


async def test_templates_are_available_and_auth_protected(client):
    token, _ = await _new_user(client)
    assert (await client.get("/api/automation/templates")).status_code == 401

    r = await client.get("/api/automation/templates", headers=auth(token))
    assert r.status_code == 200, r.text
    keys = {t["key"] for t in r.json()["templates"]}
    assert {"morning_brief", "daily_review", "mail_triage", "file_summary"} <= keys


async def test_natural_language_parser_fallback(client):
    token, _ = await _new_user(client)

    r = await client.post(
        "/api/automation/parse", json={"text": "每天 8:30 生成晨报"}, headers=auth(token)
    )
    assert r.status_code == 200, r.text
    draft = r.json()["draft"]
    assert draft["trigger_type"] == "cron"
    assert draft["cron_expr"] == "30 8 * * *"

    r = await client.post(
        "/api/automation/parse", json={"text": "每周一 9 点提醒我开周会"}, headers=auth(token)
    )
    draft = r.json()["draft"]
    assert draft["cron_expr"] == "0 9 * * 1"

    r = await client.post(
        "/api/automation/parse", json={"text": "每次上传文件后帮我总结内容"}, headers=auth(token)
    )
    draft = r.json()["draft"]
    assert draft["trigger_type"] == "event"
    assert draft["event_type"] == "file.uploaded"


async def test_create_routine_from_template_and_scope(client):
    token_a, _ = await _new_user(client)
    token_b, _ = await _new_user(client)
    bot_id = await _default_bot(client, token_a)

    r = await client.post(
        "/api/automation/from-template",
        json={"bot_id": bot_id, "template_key": "mail_triage"},
        headers=auth(token_a),
    )
    assert r.status_code == 200, r.text
    routine = r.json()
    assert routine["trigger_type"] == "event"
    assert routine["event_type"] == "mail.received"
    assert routine["event_filter"] == {"important": True}

    # Another user cannot create routines on this bot.
    r = await client.post(
        "/api/automation/from-template",
        json={"bot_id": bot_id, "template_key": "morning_brief"},
        headers=auth(token_b),
    )
    assert r.status_code == 404


async def test_dry_run_returns_plan_without_creating_a_run(client):
    from core.database.session import async_session
    from core.bots.models import BotRun
    from sqlalchemy import func, select

    token, user_id = await _new_user(client)
    bot_id = await _default_bot(client, token)
    routine = await _create_routine(client, token, bot_id)

    async with async_session() as db:
        before = (await db.execute(
            select(func.count(BotRun.id)).where(BotRun.user_id == user_id)
        )).scalar()

    r = await client.post(
        f"/api/automation/routines/{routine['id']}/dry-run", headers=auth(token)
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True
    assert body["plan"]
    assert len(body["schedule"]["next_runs"]) == 3
    assert body["schedule"]["next_runs"][0]

    async with async_session() as db:
        after = (await db.execute(
            select(func.count(BotRun.id)).where(BotRun.user_id == user_id)
        )).scalar()
    assert after == before


async def test_routine_run_history_and_stats(client):
    from core.database.session import async_session
    from core.bots.models import BotRun

    token, user_id = await _new_user(client)
    bot_id = await _default_bot(client, token)
    routine = await _create_routine(client, token, bot_id)

    async with async_session() as db:
        db.add(BotRun(
            bot_id=bot_id, user_id=user_id, routine_id=routine["id"],
            trigger="cron", status="success", input="总结今天",
            output="已完成", created_at=datetime.utcnow(),
        ))
        db.add(BotRun(
            bot_id=bot_id, user_id=user_id, routine_id=routine["id"],
            trigger="cron", status="failed", input="总结今天",
            error="timeout", created_at=datetime.utcnow(),
        ))
        await db.commit()

    r = await client.get(
        f"/api/automation/routines/{routine['id']}/runs", headers=auth(token)
    )
    assert r.status_code == 200, r.text
    runs = r.json()
    assert len(runs) == 2
    assert {x["status"] for x in runs} == {"success", "failed"}

    r = await client.get(
        f"/api/automation/routines/{routine['id']}/stats", headers=auth(token)
    )
    assert r.status_code == 200, r.text
    stats = r.json()
    assert stats["total"] == 2
    assert stats["by_status"]["failed"] == 1

    r = await client.get("/api/automation/overview", headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["routines_total"] >= 1


async def test_routine_logs_are_user_scoped(client):
    token_a, _ = await _new_user(client)
    token_b, _ = await _new_user(client)
    bot_id = await _default_bot(client, token_a)
    routine = await _create_routine(client, token_a, bot_id)

    r = await client.get(
        f"/api/automation/routines/{routine['id']}/runs", headers=auth(token_b)
    )
    assert r.status_code == 404
    r = await client.post(
        f"/api/automation/routines/{routine['id']}/dry-run", headers=auth(token_b)
    )
    assert r.status_code == 404
