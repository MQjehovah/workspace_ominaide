"""Proposal lifecycle and action execution."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, update

from ai.cognition.models import Proposal, ProposalFeedback
from core.database.session import async_session
from core.logging import get_logger

log = get_logger(__name__)

OPEN_STATUSES = ("new", "seen", "snoozed")


def _normalize_actions(
    actions: list[dict] | None = None,
    action: dict | None = None,
) -> list[dict]:
    raw = actions if isinstance(actions, list) else []
    if not raw and isinstance(action, dict):
        raw = [action]
    normalized: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or item.get("type") or "none")[:40]
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        normalized.append({
            "key": str(item.get("key") or kind)[:60],
            "label": str(item.get("label") or "")[:80],
            "kind": kind,
            "payload": payload,
        })
    return normalized


def _primary(actions: list[dict] | None) -> dict | None:
    return actions[0] if actions else None


def _out(row: Proposal) -> dict:
    actions = row.actions if isinstance(row.actions, list) else []
    return {
        "id": row.id,
        "user_id": row.user_id,
        "bot_id": row.bot_id,
        "kind": row.kind,
        "title": row.title,
        "reason": row.reason,
        "evidence": row.evidence,
        "confidence": row.confidence,
        "actions": actions,
        "primary_action": _primary(actions),
        "status": row.status,
        "channel": row.channel,
        "dedupe_key": row.dedupe_key,
        "expires_at": row.expires_at,
        "snooze_until": row.snooze_until,
        "goal_id": row.goal_id,
        "feedback": row.feedback,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


async def create_proposal(
    user_id: int,
    *,
    bot_id: int | None = None,
    kind: str = "follow_up",
    title: str,
    reason: str | None = None,
    evidence: dict | None = None,
    confidence: float = 0.5,
    actions: list[dict] | None = None,
    action: dict | None = None,
    channel: str = "now",
    dedupe_key: str | None = None,
    expires_at: datetime | None = None,
) -> Proposal:
    normalized = _normalize_actions(actions, action)
    async with async_session() as db:
        if dedupe_key:
            existing = (
                await db.execute(
                    select(Proposal).where(
                        Proposal.user_id == user_id,
                        Proposal.dedupe_key == dedupe_key,
                        Proposal.status.in_(OPEN_STATUSES),
                    ).order_by(Proposal.id.desc()).limit(1)
                )
            ).scalar_one_or_none()
            if existing is not None:
                existing.title = title[:200]
                existing.reason = (reason or "")[:500] or None
                existing.evidence = evidence
                existing.confidence = float(confidence)
                existing.actions = normalized
                existing.channel = channel
                existing.expires_at = expires_at
                await db.commit()
                await db.refresh(existing)
                return existing

        row = Proposal(
            user_id=user_id,
            bot_id=bot_id,
            kind=kind[:24],
            title=title[:200],
            reason=(reason or "")[:500] or None,
            evidence=evidence,
            confidence=float(confidence),
            actions=normalized,
            status="new",
            channel=channel,
            dedupe_key=dedupe_key,
            expires_at=expires_at,
        )
        db.add(row)
        await db.flush()
        if channel in ("notification", "voice"):
            try:
                from plugins.notifications.backend.service import create_notification

                await create_notification(
                    db,
                    user_id,
                    title[:200],
                    (reason or "")[:500] or None,
                    "proposal",
                    "/proposals",
                    actions=[
                        {"key": "accept", "label": "接受", "kind": "proposal_accept", "proposal_id": row.id},
                        {"key": "dismiss", "label": "忽略", "kind": "proposal_dismiss", "proposal_id": row.id},
                    ],
                    dedupe_key=dedupe_key or f"proposal:{row.id}",
                )
            except Exception as exc:
                log.warning(f"[proposal] notification failed: {exc}")
        await db.commit()
        await db.refresh(row)
        return row


async def expire_old(user_id: int) -> None:
    async with async_session() as db:
        await db.execute(
            update(Proposal)
            .where(
                Proposal.user_id == user_id,
                Proposal.status.in_(OPEN_STATUSES),
                Proposal.expires_at.is_not(None),
                Proposal.expires_at < datetime.now(),
            )
            .values(status="expired")
        )
        await db.commit()


async def list_proposals(
    user_id: int,
    *,
    status: str = "new",
    limit: int = 20,
) -> list[dict]:
    await expire_old(user_id)
    async with async_session() as db:
        q = select(Proposal).where(Proposal.user_id == user_id)
        if status == "open":
            q = q.where(Proposal.status.in_(OPEN_STATUSES))
        elif status and status != "all":
            q = q.where(Proposal.status == status)
        rows = list(
            (await db.execute(
                q.order_by(Proposal.created_at.desc(), Proposal.id.desc())
                .limit(max(1, min(limit, 100)))
            )).scalars().all()
        )
    return [_out(row) for row in rows]


async def get_proposal(user_id: int, proposal_id: int) -> dict | None:
    async with async_session() as db:
        row = (
            await db.execute(
                select(Proposal).where(
                    Proposal.id == proposal_id,
                    Proposal.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        return _out(row) if row is not None else None


async def _execute_action(
    db,
    user_id: int,
    row: Proposal,
    action: dict,
) -> dict:
    kind = str(action.get("kind") or "")
    payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}

    if kind == "create_todo":
        from plugins.todo.backend.schemas import TodoCreate
        from plugins.todo.backend.service import create_todo

        todo = await create_todo(
            db,
            user_id,
            TodoCreate(
                title=str(payload.get("title") or row.title)[:200],
                description=str(payload.get("description") or row.reason or "")[:500] or None,
                priority=int(payload.get("priority") or 1),
                due_date=payload.get("due_date"),
            ),
        )
        return {"action": kind, "status": "executed", "todo_id": todo.id}

    if kind == "create_goal":
        from ai.cognition.models import Goal

        goal = Goal(
            user_id=user_id,
            bot_id=row.bot_id,
            title=str(payload.get("title") or row.title)[:200],
            description=str(payload.get("description") or row.reason or ""),
            status="draft",
            priority=int(payload.get("priority") or 50),
            context={"proposal_id": row.id, **(payload.get("context") or {})},
            success_criteria=payload.get("success_criteria"),
            created_by="proposal",
        )
        db.add(goal)
        await db.flush()
        return {"action": kind, "status": "executed", "goal_id": goal.id}

    if kind in ("link", "open", "none", ""):
        return {"action": kind or "none", "status": "accepted"}

    # Other action kinds are recorded but not auto-executed in this phase.
    return {"action": kind, "status": "accepted", "note": "action kind not executed"}


async def act_proposal(
    user_id: int,
    proposal_id: int,
    *,
    action: str,
    snooze_minutes: int = 60,
) -> dict | None:
    async with async_session() as db:
        row = (
            await db.execute(
                select(Proposal).where(
                    Proposal.id == proposal_id,
                    Proposal.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None

        now = datetime.now()
        result: dict[str, Any] = {"proposal_id": proposal_id}

        if action == "seen":
            if row.status == "new":
                row.status = "seen"
            result.update(status=row.status, action=action)
        elif action == "dismiss":
            row.status = "dismissed"
            result.update(status=row.status, action=action)
        elif action == "snooze":
            row.status = "snoozed"
            row.snooze_until = now + timedelta(minutes=max(5, int(snooze_minutes)))
            result.update(status=row.status, action=action, snooze_until=row.snooze_until)
        elif action in ("accept", "execute"):
            row.status = "accepted"
            actions = row.actions if isinstance(row.actions, list) else []
            primary = _primary(actions)
            if primary:
                executed = await _execute_action(db, user_id, row, primary)
                result.update(executed)
                if executed.get("status") == "executed":
                    row.status = "executed"
                else:
                    result["status"] = row.status
            else:
                from ai.cognition.models import Goal

                goal = Goal(
                    user_id=user_id,
                    bot_id=row.bot_id,
                    title=row.title,
                    description=row.reason,
                    status="draft",
                    context={"proposal_id": row.id},
                    created_by="proposal",
                )
                db.add(goal)
                await db.flush()
                result.update(status=row.status, action="create_goal", goal_id=goal.id)
            if action == "execute":
                result["requested"] = "execute"
        else:
            return None

        row.feedback = {
            **(row.feedback or {}),
            "last_action": action,
            "acted_at": now.isoformat(timespec="seconds"),
        }
        db.add(ProposalFeedback(
            proposal_id=row.id,
            user_id=user_id,
            action=action,
            note=None,
        ))
        await db.commit()
        await db.refresh(row)
        result["status"] = row.status
        return result
