"""Memory x situation proposal mining."""

import random
import string

from conftest import auth


async def _new_user(client):
    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"miner_{suffix}"
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


async def test_memory_record_keeps_structured_data(client):
    token, user_id = await _new_user(client)
    from ai.memory.models import MemoryRecord
    from core.database.session import async_session

    async with async_session() as db:
        row = MemoryRecord(
            user_id=user_id,
            kind="commitment",
            content="周五前把报价发给张三",
            normalized="周五前把报价发给张三",
            data={"person": "张三", "due_at": "2026-11-13", "state": "open"},
        )
        db.add(row)
        await db.commit()
        assert row.data["person"] == "张三"


async def test_commitment_and_event_create_proposal(client):
    token, user_id = await _new_user(client)
    from datetime import datetime, timedelta
    from ai.memory.models import MemoryRecord
    from plugins.schedule.backend.models import Event
    from core.database.session import async_session
    from ai.cognition.miner import mine_user

    async with async_session() as db:
        db.add(Event(
            user_id=user_id,
            title="和张三开预算评审会",
            start_time=datetime.now() + timedelta(hours=2),
        ))
        db.add(MemoryRecord(
            user_id=user_id,
            kind="commitment",
            content="周五前把报价发给张三",
            normalized="周五前把报价发给张三",
            confidence=90,
            data={
                "person": "张三",
                "project": "预算",
                "state": "open",
                "due_at": "2026-11-13",
                "quote": "我周五前把报价发你",
            },
        ))
        await db.commit()

    result = await mine_user(user_id)
    assert result["created"] >= 1


async def test_memory_without_situation_is_rejected(client):
    token, user_id = await _new_user(client)
    from ai.cognition.miner import mine_user

    result = await mine_user(user_id)
    assert result["created"] == 0


async def test_memory_write_enqueues_mining_job(client, monkeypatch):
    token, user_id = await _new_user(client)
    from ai.memory import service as memory_service
    from ai.memory.models import MemoryCandidate
    from core.database.session import async_session

    async with async_session() as db:
        candidate = MemoryCandidate(
            user_id=user_id,
            kind="fact",
            content="测试记忆",
            normalized="测试记忆",
            confidence=90,
        )
        db.add(candidate)
        await db.commit()
        await db.refresh(candidate)
        candidate_id = candidate.id

    calls = []

    async def fake_enqueue(target_user_id):
        calls.append(target_user_id)

    monkeypatch.setattr("ai.cognition.jobs.enqueue_mine_user", fake_enqueue)
    await memory_service.approve_candidate(user_id, candidate_id)
    assert calls == [user_id]


def test_quality_gate_rejects_secret_and_missing_quote():
    from ai.cognition.miner import MiningCandidate
    from ai.cognition.quality import evaluate

    base = dict(
        memory_id=1,
        kind="memory_commitment_event",
        title="x",
        reason="x",
        confidence=0.9,
        action={"kind": "create_todo"},
        evidence={"quote": "我周五前把报价发你", "state": "open"},
        situation_ref={"type": "event", "id": 1},
    )
    secret = MiningCandidate(
        **{**base, "evidence": {**base["evidence"], "sensitivity": "secret"}}
    )
    passed, score, reasons = evaluate(secret)
    assert passed is False
    assert any("secret" in reason for reason in reasons)

    no_quote = MiningCandidate(**{**base, "evidence": {"state": "open"}})
    passed, score, reasons = evaluate(no_quote)
    assert passed is False
    assert any("quote" in reason for reason in reasons)

    weak = MiningCandidate(**{**base, "confidence": 0.2})
    passed, score, reasons = evaluate(weak)
    assert passed is False
    assert any("confidence" in reason for reason in reasons)


async def test_resolved_memory_closes_existing_proposal(client):
    token, user_id = await _new_user(client)
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from ai.memory.models import MemoryRecord
    from ai.memory.service import update_record
    from ai.cognition.miner import mine_user
    from ai.cognition.models import Proposal
    from plugins.schedule.backend.models import Event
    from core.database.session import async_session

    async with async_session() as db:
        db.add(Event(
            user_id=user_id,
            title="和张三开报价评审会",
            start_time=datetime.now() + timedelta(hours=2),
        ))
        memory = MemoryRecord(
            user_id=user_id,
            kind="commitment",
            content="闭环测试：会前发报价",
            normalized="闭环测试：会前发报价",
            confidence=90,
            data={
                "person": "张三",
                "state": "open",
                "quote": "我周五前把报价发你",
            },
        )
        db.add(memory)
        await db.commit()
        memory_id = memory.id

    await mine_user(user_id)
    async with async_session() as db:
        proposal = (await db.execute(
            select(Proposal).where(
                Proposal.user_id == user_id,
                Proposal.dedupe_key.like(f"memory:{memory_id}:%"),
            ).limit(1)
        )).scalar_one()
        assert proposal.status in ("new", "seen", "snoozed")

    await update_record(user_id, memory_id, state="resolved")
    async with async_session() as db:
        proposal = (await db.execute(
            select(Proposal).where(Proposal.id == proposal.id)
        )).scalar_one()
        assert proposal.status == "expired"


async def test_repeated_mining_does_not_duplicate_proposals(client):
    token, user_id = await _new_user(client)
    from datetime import datetime, timedelta
    from sqlalchemy import func, select
    from ai.memory.models import MemoryRecord
    from ai.cognition.miner import mine_user
    from ai.cognition.models import Proposal
    from plugins.schedule.backend.models import Event
    from core.database.session import async_session

    async with async_session() as db:
        db.add(Event(
            user_id=user_id,
            title="和赵六开预算会",
            start_time=datetime.now() + timedelta(hours=2),
        ))
        memory = MemoryRecord(
            user_id=user_id,
            kind="commitment",
            content="去重测试：会前发预算",
            normalized="去重测试：会前发预算",
            confidence=90,
            data={
                "person": "赵六",
                "state": "open",
                "quote": "会前把预算发你",
            },
        )
        db.add(memory)
        await db.commit()
        memory_id = memory.id

    first = await mine_user(user_id)
    second = await mine_user(user_id)
    assert first["created"] == 1
    assert second["created"] == 0

    async with async_session() as db:
        count = (await db.execute(
            select(func.count()).select_from(Proposal).where(
                Proposal.user_id == user_id,
                Proposal.dedupe_key.like(f"memory:{memory_id}:%"),
            )
        )).scalar_one()
    assert count == 1


async def test_proposal_link_action_returns_url(client):
    from ai.cognition.proposals import _execute_action

    result = await _execute_action(
        None,
        1,
        type("P", (), {"id": 1, "title": "x", "bot_id": None})(),
        {"kind": "open", "payload": {"link": "/chat?session_id=abc"}},
    )
    assert result["link"] == "/chat?session_id=abc"
