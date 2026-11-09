"""Memory x situation proposal mining.

Every insight proposal must cite a memory and a current situation fact.
Situation-only reminders stay in the existing activity pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select

from ai.cognition.models import Proposal
from ai.cognition.proposals import create_proposal
from ai.cognition.quality import evaluate
from ai.cognition.situation import get_situation
from ai.entities.service import normalize_name
from ai.memory.models import MemoryRecord
from core.database.session import async_session
from core.logging import get_logger

log = get_logger(__name__)

OPEN_PROPOSAL_STATUSES = ("new", "seen", "snoozed", "accepted", "executing")


@dataclass
class MiningCandidate:
    memory_id: int
    kind: str
    title: str
    reason: str
    confidence: float
    action: dict
    evidence: dict
    situation_ref: dict | None
    source: str = "memory"


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _event_time(event: dict) -> datetime | None:
    return _parse_dt(event.get("time") or event.get("start_time"))


def _int_id(value) -> int:
    if isinstance(value, int):
        return value
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return int(digits) if digits else 0


def _memory_names(memory: MemoryRecord) -> list[str]:
    data = memory.data if isinstance(memory.data, dict) else {}
    names = []
    for key in ("person", "project", "topic"):
        value = str(data.get(key) or "").strip()
        if value:
            names.append(value)
    return names


def _matches_text(text: str | None, names: list[str]) -> bool:
    if not text or not names:
        return False
    normalized = normalize_name(text)
    return any(normalize_name(name) and normalize_name(name) in normalized for name in names)


def _quote(memory: MemoryRecord) -> str:
    data = memory.data if isinstance(memory.data, dict) else {}
    return str(data.get("quote") or memory.content or "")[:200]


def _base_evidence(memory: MemoryRecord, rule: str) -> dict:
    return {
        "memory_id": memory.id,
        "quote": _quote(memory),
        "state": "open",
        "rule": rule,
    }


def _commitment_event_candidate(
    memory: MemoryRecord,
    snapshot: dict,
) -> MiningCandidate | None:
    names = _memory_names(memory)
    if not names:
        return None
    now = datetime.now()
    horizon = now + timedelta(hours=48)
    for event in snapshot.get("calendar") or []:
        when = _event_time(event)
        if when is None or when < now - timedelta(hours=1) or when > horizon:
            continue
        if not _matches_text(str(event.get("title") or ""), names):
            continue
        due = when.isoformat(timespec="minutes")
        return MiningCandidate(
            memory_id=memory.id,
            kind="memory_commitment_event",
            title=f"会前完成：{memory.content[:60]}",
            reason=f"与「{event.get('title')}」相关，建议会前完成",
            confidence=float(memory.confidence or 60) / 100,
            action={
                "key": "create_todo",
                "label": "创建待办",
                "kind": "create_todo",
                "payload": {
                    "title": memory.content[:200],
                    "description": _quote(memory),
                    "due_date": due,
                },
            },
            evidence={
                **_base_evidence(memory, "commitment_event"),
                "situation_ref": {
                    "type": "event",
                    "id": _int_id(event.get("id")),
                    "title": event.get("title"),
                },
            },
            situation_ref={
                "type": "event",
                "id": _int_id(event.get("id")),
                "title": event.get("title"),
            },
        )
    return None


def _commitment_due_candidate(memory: MemoryRecord) -> MiningCandidate | None:
    data = memory.data if isinstance(memory.data, dict) else {}
    due = _parse_dt(data.get("due_at"))
    if due is None:
        return None
    now = datetime.now()
    if due > now + timedelta(hours=24):
        return None
    state = "overdue" if due < now else "due_soon"
    return MiningCandidate(
        memory_id=memory.id,
        kind="memory_commitment_due",
        title=f"该处理了：{memory.content[:60]}",
        reason="承诺临近截止" if state == "due_soon" else "承诺已经逾期",
        confidence=float(memory.confidence or 60) / 100,
        action={
            "key": "create_todo",
            "label": "创建待办",
            "kind": "create_todo",
            "payload": {
                "title": memory.content[:200],
                "description": _quote(memory),
                "due_date": due.isoformat(timespec="minutes"),
            },
        },
        evidence={
            **_base_evidence(memory, "commitment_due"),
            "situation_ref": {
                "type": "time",
                "due_at": due.isoformat(timespec="minutes"),
                "state": state,
            },
        },
        situation_ref={
            "type": "time",
            "due_at": due.isoformat(timespec="minutes"),
            "state": state,
        },
    )


def _open_loop_candidate(
    memory: MemoryRecord,
    snapshot: dict,
) -> MiningCandidate | None:
    data = memory.data if isinstance(memory.data, dict) else {}
    created = memory.created_at or memory.updated_at
    if created is not None and created > datetime.now() - timedelta(hours=24):
        return None
    names = _memory_names(memory)
    activities = (snapshot.get("recent") or {}).get("activities") or []
    trigger = None
    for activity in activities:
        if _matches_text(str(activity.get("summary") or ""), names):
            trigger = activity
            break
    if trigger is None:
        return None
    session_id = str(data.get("session_id") or "")
    action = (
        {
            "key": "open",
            "label": "查看对话",
            "kind": "open",
            "payload": {"link": f"/chat?session_id={session_id}"},
        }
        if session_id
        else {
            "key": "create_todo",
            "label": "创建跟进",
            "kind": "create_todo",
            "payload": {
                "title": f"跟进：{memory.content[:180]}",
                "description": _quote(memory),
            },
        }
    )
    return MiningCandidate(
        memory_id=memory.id,
        kind="memory_open_loop",
        title=f"还没有闭环：{memory.content[:60]}",
        reason="最近又提到了这件事，可以继续推进",
        confidence=float(memory.confidence or 60) / 100,
        action=action,
        evidence={
            **_base_evidence(memory, "open_loop"),
            "situation_ref": {
                "type": "activity",
                "id": _int_id(trigger.get("id")),
            },
        },
        situation_ref={
            "type": "activity",
            "id": _int_id(trigger.get("id")),
        },
    )


async def _duplicate(db, user_id: int, candidate: MiningCandidate) -> bool:
    rule = str(candidate.evidence.get("rule") or candidate.kind)
    dedupe = f"memory:{candidate.memory_id}:{rule}"
    existing = (await db.execute(
        select(Proposal.id).where(
            Proposal.user_id == user_id,
            Proposal.dedupe_key == dedupe,
            Proposal.status.in_(OPEN_PROPOSAL_STATUSES),
        ).limit(1)
    )).scalar_one_or_none()
    if existing is not None:
        return True

    payload = candidate.action.get("payload") or {}
    title = str(payload.get("title") or "").strip()
    if title:
        from plugins.todo.backend.models import PluginTodoItem

        todo = (await db.execute(
            select(PluginTodoItem.id).where(
                PluginTodoItem.user_id == user_id,
                PluginTodoItem.status == "pending",
                PluginTodoItem.title == title[:200],
            ).limit(1)
        )).scalar_one_or_none()
        if todo is not None:
            return True
    return False


async def mine_user(user_id: int) -> dict:
    snapshot = await get_situation(user_id, force=True)
    async with async_session() as db:
        memories = list((await db.execute(
            select(MemoryRecord).where(
                MemoryRecord.user_id == user_id,
                MemoryRecord.status == "active",
                MemoryRecord.kind.in_(("commitment", "open_loop")),
            )
        )).scalars().all())

        created = 0
        rejected = 0
        candidates = 0
        for memory in memories:
            data = memory.data if isinstance(memory.data, dict) else {}
            if str(data.get("state") or "open") != "open":
                continue
            proposals: list[MiningCandidate] = []
            if memory.kind == "commitment":
                event_candidate = _commitment_event_candidate(memory, snapshot)
                if event_candidate is not None:
                    proposals.append(event_candidate)
                due_candidate = _commitment_due_candidate(memory)
                if due_candidate is not None:
                    proposals.append(due_candidate)
            elif memory.kind == "open_loop":
                loop_candidate = _open_loop_candidate(memory, snapshot)
                if loop_candidate is not None:
                    proposals.append(loop_candidate)

            for candidate in proposals:
                candidates += 1
                if await _duplicate(db, user_id, candidate):
                    rejected += 1
                    continue
                passed, score, reasons = evaluate(candidate)
                if not passed:
                    rejected += 1
                    log.debug(
                        f"[miner] rejected {candidate.kind} memory={candidate.memory_id}: {reasons}"
                    )
                    continue
                await create_proposal(
                    user_id,
                    kind=candidate.kind,
                    title=candidate.title,
                    reason=candidate.reason,
                    evidence=candidate.evidence,
                    confidence=candidate.confidence,
                    actions=[candidate.action],
                    channel="now",
                    source="memory",
                    quality_score=score,
                    dedupe_key=f"memory:{candidate.memory_id}:{candidate.evidence.get('rule')}",
                    expires_at=datetime.now() + timedelta(days=14),
                )
                created += 1

    return {"created": created, "rejected": rejected, "candidates": candidates}
