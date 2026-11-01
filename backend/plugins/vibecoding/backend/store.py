import json
import time
from typing import Any

from sqlalchemy import select

from core.database.session import async_session

MAX_EVENTS = 600
MAX_EVENT_CHARS = 240_000
MAX_MESSAGES_CHARS = 400_000
MAX_OUTPUT_CHARS = 40_000


def _dumps(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return json.dumps(str(value), ensure_ascii=False)


def _loads(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _trim_events(events: list[dict]) -> list[dict]:
    """Keep the most recent events, bounded by both count and total size."""
    if len(events) > MAX_EVENTS:
        events = events[-MAX_EVENTS:]
    total = 0
    kept: list[dict] = []
    for event in reversed(events):
        total += len(json.dumps(event, ensure_ascii=False, default=str))
        if total > MAX_EVENT_CHARS:
            break
        kept.append(event)
    kept.reverse()
    return kept


def trim_messages(messages: list[dict], budget: int = MAX_MESSAGES_CHARS) -> list[dict]:
    """Keep a valid, most-recent slice of a conversation for later continuation.

    The slice must start at a ``user`` message so tool_call/tool pairs never get
    severed, and the system prompt is always preserved separately.
    """
    if not messages:
        return []
    system = messages[0] if messages[0].get("role") == "system" else None
    body = messages[1:] if system else messages[:]

    used = 0
    cut = 0
    for index in range(len(body) - 1, -1, -1):
        used += len(json.dumps(body[index], ensure_ascii=False, default=str))
        if used > budget:
            cut = index + 1
            break
    else:
        cut = 0

    # Never start in the middle of an assistant/tool exchange.
    while cut < len(body) and body[cut].get("role") not in ("user",):
        cut += 1
    if cut >= len(body):
        cut = max(len(body) - 1, 0)

    trimmed = ([system] if system else []) + body[cut:]
    return trimmed


def task_to_dict(row) -> dict:
    events = _loads(row.events, [])
    return {
        "task_id": row.id,
        "parent_id": row.parent_id,
        "device_id": "server",
        "tool": "omniaide",
        "engine": row.engine or "server",
        "project": row.project,
        "project_name": row.project_name,
        "source": row.source,
        "input": row.instruction or "",
        "status": row.status,
        "started_ts": row.started_ts,
        "ended_ts": row.ended_ts,
        "duration_ms": row.duration_ms,
        "code": row.code,
        "output": row.output or "",
        "error": row.error,
        "turns": row.turns or 0,
        "branch": row.branch,
        "commit_sha": row.commit_sha,
        "pr_url": row.pr_url,
        "event_count": len(events),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def create_task(user_id: int, task_id: str, project: str, instruction: str,
                      source: str, project_name: str | None = None,
                      parent_id: str | None = None, engine: str = "server") -> None:
    from plugins.vibecoding.backend.models import CodingTask

    async with async_session() as db:
        db.add(CodingTask(
            id=task_id,
            user_id=user_id,
            parent_id=parent_id,
            project=project,
            project_name=project_name,
            source=source,
            engine=engine,
            instruction=instruction,
            status="running",
            started_ts=int(time.time() * 1000),
            turns=0,
            events=_dumps([]),
        ))
        await db.commit()


async def update_task(task_id: str, **fields) -> None:
    """Update a task row. Unknown keys are ignored; failures are logged, never raised."""
    from plugins.vibecoding.backend.models import CodingTask

    allowed = {
        "status", "code", "duration_ms", "turns", "output", "error",
        "branch", "commit_sha", "pr_url", "ended_ts", "started_ts",
    }
    values = {}
    for key, value in fields.items():
        if key == "events":
            values["events"] = _dumps(_trim_events(value or []))
        elif key == "messages":
            values["messages"] = _dumps(trim_messages(value or []))
        elif key in allowed:
            values[key] = value

    if not values:
        return
    async with async_session() as db:
        row = await db.get(CodingTask, task_id)
        if not row:
            return
        for key, value in values.items():
            setattr(row, key, value)
        await db.commit()


async def set_messages(task_id: str, messages: list[dict]) -> None:
    await update_task(task_id, messages=messages)


async def get_task(task_id: str, user_id: int):
    from plugins.vibecoding.backend.models import CodingTask

    async with async_session() as db:
        result = await db.execute(
            select(CodingTask).where(CodingTask.id == task_id, CodingTask.user_id == user_id)
        )
        return result.scalar_one_or_none()


async def get_task_detail(task_id: str, user_id: int) -> dict | None:
    row = await get_task(task_id, user_id)
    if not row:
        return None
    task = task_to_dict(row)
    task["events"] = _loads(row.events, [])
    return task


async def get_task_messages(task_id: str, user_id: int) -> list[dict]:
    row = await get_task(task_id, user_id)
    if not row:
        return []
    return _loads(row.messages, [])


async def list_tasks(user_id: int, limit: int = 50, project: str | None = None) -> list[dict]:
    from plugins.vibecoding.backend.models import CodingTask

    limit = max(1, min(int(limit or 50), 200))
    stmt = select(CodingTask).where(CodingTask.user_id == user_id)
    if project:
        stmt = stmt.where(CodingTask.project == project)
    stmt = stmt.order_by(CodingTask.started_ts.desc()).limit(limit)
    async with async_session() as db:
        rows = (await db.execute(stmt)).scalars().all()
    return [task_to_dict(row) for row in rows]


async def mark_orphans_cancelled() -> None:
    """Tasks left 'running' by a restart can never resume: mark them cancelled."""
    from sqlalchemy import update
    from plugins.vibecoding.backend.models import CodingTask

    async with async_session() as db:
        await db.execute(
            update(CodingTask)
            .where(CodingTask.status == "running")
            .values(status="cancelled", ended_ts=int(time.time() * 1000))
        )
        await db.commit()
