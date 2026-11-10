"""Unified session and message persistence."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select

from core.database.session import async_session
from core.sessions.models import Session, SessionMessage


def _session_out(row: Session) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "session_id": row.session_id,
        "bot_id": row.bot_id,
        "title": row.title,
        "kind": row.kind,
        "objective": row.objective,
        "status": row.status,
        "metadata": row.meta or {},
        "active_run_id": row.active_run_id,
        "last_message_at": row.last_message_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _message_out(row: SessionMessage) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "session_id": row.session_id,
        "bot_id": row.bot_id,
        "run_id": row.run_id,
        "role": row.role,
        "kind": row.kind,
        "content": row.content,
        "metadata": row.meta or {},
        "created_at": row.created_at,
    }


def new_session_id(kind: str = "session") -> str:
    return f"{kind}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"


async def get_session(user_id: int, session_id: str) -> dict | None:
    async with async_session() as db:
        row = (
            await db.execute(
                select(Session).where(
                    Session.user_id == user_id,
                    Session.session_id == session_id,
                )
            )
        ).scalar_one_or_none()
        return _session_out(row) if row else None


async def ensure_session(
    user_id: int,
    session_id: str,
    *,
    bot_id: int | None = None,
    kind: str | None = None,
    title: str | None = None,
    objective: str | None = None,
    metadata: dict | None = None,
) -> dict:
    async with async_session() as db:
        row = (
            await db.execute(
                select(Session).where(
                    Session.user_id == user_id,
                    Session.session_id == session_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = Session(
                user_id=user_id,
                session_id=session_id,
                bot_id=bot_id,
                title=title,
                kind=kind or "chat",
                objective=objective,
                status="active",
                meta=metadata or {},
            )
            db.add(row)
        else:
            if bot_id is not None:
                row.bot_id = bot_id
            if kind:
                row.kind = kind
            # Title/objective belong to the session, not to each new Run.
            # Use update_session explicitly when the user renames the session.
            if metadata:
                row.meta = {**(row.meta or {}), **metadata}
        await db.commit()
        await db.refresh(row)
        return _session_out(row)


async def create_session(
    user_id: int,
    *,
    bot_id: int | None = None,
    kind: str | None = None,
    title: str | None = None,
    objective: str | None = None,
    metadata: dict | None = None,
    session_id: str | None = None,
) -> dict:
    session_id = session_id or new_session_id(kind or "session")
    return await ensure_session(
        user_id,
        session_id,
        bot_id=bot_id,
        kind=kind,
        title=title,
        objective=objective,
        metadata=metadata,
    )


async def list_sessions(user_id: int, *, kind: str | None = None, limit: int = 100) -> list[dict]:
    async with async_session() as db:
        query = select(Session).where(Session.user_id == user_id)
        if kind:
            query = query.where(Session.kind == kind)
        rows = list(
            (await db.execute(query.order_by(Session.updated_at.desc()).limit(max(1, min(limit, 200)))))
            .scalars()
            .all()
        )
        return [_session_out(row) for row in rows]


async def update_session(user_id: int, session_id: str, **values: Any) -> dict | None:
    async with async_session() as db:
        row = (
            await db.execute(
                select(Session).where(
                    Session.user_id == user_id,
                    Session.session_id == session_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        for key, value in values.items():
            if key == "metadata":
                row.meta = {**(row.meta or {}), **(value or {})}
            elif hasattr(row, key) and key not in {"id", "user_id", "session_id"}:
                setattr(row, key, value)
        row.updated_at = datetime.now()
        await db.commit()
        await db.refresh(row)
        return _session_out(row)


async def delete_session(user_id: int, session_id: str) -> bool:
    async with async_session() as db:
        row = (
            await db.execute(
                select(Session).where(
                    Session.user_id == user_id,
                    Session.session_id == session_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        await db.execute(
            delete(SessionMessage).where(
                SessionMessage.user_id == user_id,
                SessionMessage.session_id == session_id,
            )
        )
        await db.delete(row)
        await db.commit()
        return True


async def add_message(
    user_id: int,
    session_id: str,
    role: str,
    content: str,
    *,
    bot_id: int | None = None,
    run_id: int | None = None,
    kind: str = "text",
    metadata: dict | None = None,
) -> dict:
    await ensure_session(user_id, session_id, bot_id=bot_id)
    async with async_session() as db:
        row = SessionMessage(
            user_id=user_id,
            session_id=session_id,
            bot_id=bot_id,
            run_id=run_id,
            role=role,
            kind=kind,
            content=content,
            meta=metadata or {},
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        session = (
            await db.execute(
                select(Session).where(
                    Session.user_id == user_id,
                    Session.session_id == session_id,
                )
            )
        ).scalar_one_or_none()
        if session is not None:
            session.last_message_at = row.created_at or datetime.now()
            session.updated_at = datetime.now()
            await db.commit()
        return _message_out(row)


async def list_messages(
    user_id: int,
    session_id: str,
    *,
    limit: int = 100,
    before_id: int | None = None,
) -> list[dict]:
    async with async_session() as db:
        query = select(SessionMessage).where(
            SessionMessage.user_id == user_id,
            SessionMessage.session_id == session_id,
        )
        if before_id is not None:
            query = query.where(SessionMessage.id < before_id)
        rows = list(
            (await db.execute(query.order_by(SessionMessage.id.desc()).limit(max(1, min(limit, 500)))))
            .scalars()
            .all()
        )
        return [_message_out(row) for row in reversed(rows)]


async def list_runs(user_id: int, session_id: str, *, limit: int = 50) -> list[dict]:
    from ai.bots.models import Run

    async with async_session() as db:
        rows = list(
            (
                await db.execute(
                    select(Run)
                    .where(Run.user_id == user_id, Run.session_id == session_id)
                    .order_by(Run.id.desc())
                    .limit(max(1, min(limit, 200)))
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": row.id,
                "trigger": row.trigger,
                "agent": row.agent,
                "status": row.status,
                "input": row.input,
                "output": row.output,
                "error": row.error,
                "created_at": row.created_at,
                "finished_at": row.finished_at,
            }
            for row in rows
        ]


async def set_active_run(user_id: int, session_id: str, run_id: int | None, status: str | None = None) -> None:
    values: dict[str, Any] = {"active_run_id": run_id}
    if status:
        values["status"] = status
    await update_session(user_id, session_id, **values)
