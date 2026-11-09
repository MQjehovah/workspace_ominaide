"""Execute unified BotRoutine automations.

One trigger -> one AutomationRun -> ordered actions. Deterministic actions run
without an LLM; an ``agent`` action dispatches a Run.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select, update

from ai.automation.dsl import evaluate_conditions, spec_from_routine
from ai.automation.models import AutomationRun
from ai.bots.models import Bot, BotRoutine
from core.database.session import async_session
from core.logging import get_logger

log = get_logger(__name__)


def build_context(
    routine: BotRoutine,
    trigger_type: str,
    *,
    event=None,
    manual: dict | None = None,
    scheduled_for: datetime | None = None,
) -> dict:
    now = datetime.now()
    context = {
        "trigger": {
            "type": trigger_type,
            "routine_id": routine.id,
            "occurred_at": now.isoformat(timespec="seconds"),
            "scheduled_for": scheduled_for.isoformat(timespec="seconds") if scheduled_for else None,
        },
        "now": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
        "weekday": now.weekday(),
        "user": {"id": routine.user_id},
        "manual": manual or {},
    }
    if event is not None:
        context["event"] = {
            "id": getattr(event, "id", None),
            "event_type": getattr(event, "event_type", None),
            "entity_type": getattr(event, "entity_type", None),
            "entity_id": getattr(event, "entity_id", None),
            "summary": getattr(event, "summary", None),
            "details": getattr(event, "details", None) or {},
        }
    return context


def make_idempotency_key(
    routine_id: int,
    trigger_type: str,
    *,
    event_id: int | None = None,
    scheduled_for: datetime | None = None,
) -> str:
    if trigger_type == "event" and event_id is not None:
        return f"automation:{routine_id}:event:{event_id}"
    if trigger_type == "schedule":
        stamp = (scheduled_for or datetime.now()).strftime("%Y%m%d%H%M")
        return f"automation:{routine_id}:cron:{stamp}"
    return f"automation:{routine_id}:manual:{uuid4().hex}"


async def _load_routine(routine_id: int) -> BotRoutine | None:
    async with async_session() as db:
        return await db.get(BotRoutine, routine_id)


async def _existing_run(key: str) -> AutomationRun | None:
    async with async_session() as db:
        return (
            await db.execute(
                select(AutomationRun).where(AutomationRun.idempotency_key == key)
            )
        ).scalar_one_or_none()


async def _new_run(
    routine: BotRoutine,
    trigger_type: str,
    context: dict,
    spec: dict,
    key: str,
    status: str,
) -> AutomationRun:
    async with async_session() as db:
        run = AutomationRun(
            routine_id=routine.id,
            user_id=routine.user_id,
            trigger_type=trigger_type,
            trigger_context=context,
            spec_snapshot=spec,
            status=status,
            idempotency_key=key,
            started_at=datetime.now() if status == "running" else None,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run


async def _finish_run(
    run_id: int,
    routine: BotRoutine,
    *,
    status: str,
    action_results: list[dict],
    agent_run_id: int | None = None,
    error: str | None = None,
) -> None:
    async with async_session() as db:
        run = await db.get(AutomationRun, run_id)
        if run is not None:
            run.status = status
            run.action_results = action_results
            run.agent_run_id = agent_run_id
            run.error = (error or "")[:3000] or None
            run.finished_at = datetime.now()
        await db.execute(
            update(BotRoutine)
            .where(BotRoutine.id == routine.id)
            .values(
                last_run_at=datetime.now(),
                last_status=status,
                last_error=(error or "")[:3000] or None,
                run_count=(BotRoutine.run_count or 0) + 1,
            )
        )
        await db.commit()


async def _run_notify(user_id: int, params: dict) -> dict:
    from plugins.notifications.backend import service as notification_service
    from plugins.notifications.backend.router import notify_user

    title = str(params.get("title") or params.get("text") or "自动化通知")[:200]
    body = params.get("body") or params.get("text")
    link = params.get("link")
    async with async_session() as db:
        row = await notification_service.create_notification(
            db, user_id, title=title, body=body, link=link, type="automation",
            dedupe_key=params.get("dedupe_key"),
        )
        await db.commit()
        notification_id = row.id
    await notify_user(user_id, {
        "type": "new_notification",
        "title": title,
        "body": body,
        "link": link,
    })
    return {"notification_id": notification_id, "title": title}


async def _run_todo(user_id: int, params: dict) -> dict:
    from plugins.todo.backend.schemas import TodoCreate
    from plugins.todo.backend.service import create_todo

    req = TodoCreate(**params)
    async with async_session() as db:
        row = await create_todo(db, user_id, req)
        await db.commit()
        await db.refresh(row)
        return {"todo_id": row.id, "title": row.title}


async def _run_event(user_id: int, params: dict) -> dict:
    from plugins.schedule.backend.schemas import EventCreate
    from plugins.schedule.backend.service import create_event

    req = EventCreate(**params)
    async with async_session() as db:
        row = await create_event(db, user_id, req)
        await db.commit()
        await db.refresh(row)
        return {"event_id": row.id, "title": row.title}


async def _run_note(user_id: int, params: dict) -> dict:
    from plugins.notes.backend.schemas import NoteCreate
    from plugins.notes.backend.service import create_note

    req = NoteCreate(
        title=str(params.get("title") or "自动化笔记")[:500],
        content=str(params.get("content") or ""),
        parent_id=params.get("parent_id"),
    )
    async with async_session() as db:
        row = await create_note(db, user_id, req)
        await db.commit()
        await db.refresh(row)
        return {"note_id": row.id, "title": row.title}


async def _run_skill(routine: BotRoutine, params: dict) -> dict:
    from ai.skills import runtime

    skill_key = str(params.get("skill_key") or "").strip()
    if not skill_key:
        raise ValueError("skill action requires params.skill_key")
    input_data = params.get("input")
    if not isinstance(input_data, dict):
        input_data = {}
    result = await runtime.run_skill(
        routine.user_id,
        routine.bot_id,
        skill_key,
        input_data,
    )
    output = result.get("output") if isinstance(result, dict) else None
    summary = ""
    if isinstance(output, dict):
        summary = str(output.get("summary") or "")
    return {
        "skill_key": skill_key,
        "skill_run_id": result.get("run_id") if isinstance(result, dict) else None,
        "summary": summary[:500],
    }


async def _run_agent(routine: BotRoutine, params: dict) -> dict:
    from ai.bots import runner

    prompt = str(params.get("prompt") or routine.prompt or routine.name).strip()
    async with async_session() as db:
        bot = await db.get(Bot, routine.bot_id)
    if bot is None:
        raise ValueError("bot not found")
    run = await runner.create_run(
        routine.user_id,
        bot,
        prompt,
        trigger="automation",
        routine_id=routine.id,
        idempotency_key=f"automation-agent:{routine.id}:{uuid4().hex}",
    )
    return {"agent_run_id": run.id, "prompt": prompt[:300]}


async def _execute_action(routine: BotRoutine, action: dict) -> dict:
    action_type = str(action.get("type") or "")
    params = action.get("params") or {}
    if action_type == "notify":
        return await _run_notify(routine.user_id, params)
    if action_type == "todo":
        return await _run_todo(routine.user_id, params)
    if action_type == "event":
        return await _run_event(routine.user_id, params)
    if action_type == "note":
        return await _run_note(routine.user_id, params)
    if action_type == "agent":
        return await _run_agent(routine, params)
    if action_type == "skill":
        return await _run_skill(routine, params)
    raise ValueError(f"unsupported action: {action_type}")


async def execute_automation(
    routine_id: int,
    trigger_type: str,
    *,
    event=None,
    manual: dict | None = None,
    scheduled_for: datetime | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict:
    """Run one automation occurrence. Returns the AutomationRun dict or plan."""
    routine = await _load_routine(routine_id)
    if routine is None:
        raise ValueError("routine not found")
    if not routine.enabled and not force:
        return {"status": "disabled", "routine_id": routine_id}

    spec = spec_from_routine(routine)
    context = build_context(
        routine, trigger_type, event=event, manual=manual,
        scheduled_for=scheduled_for,
    )
    key = make_idempotency_key(
        routine.id, trigger_type,
        event_id=getattr(event, "id", None),
        scheduled_for=scheduled_for,
    )
    existing = await _existing_run(key)
    if existing is not None:
        return {"status": "skipped", "reason": "duplicate", "run_id": existing.id}

    matched, condition_results = evaluate_conditions(spec, context)
    if dry_run:
        return {
            "dry_run": True,
            "matched": matched,
            "conditions": condition_results,
            "spec": spec,
            "context": context,
        }

    if not matched and not force:
        run = await _new_run(routine, trigger_type, context, spec, key, "skipped")
        await _finish_run(
            run.id, routine, status="skipped",
            action_results=[{"type": "conditions", "results": condition_results}],
        )
        return {"status": "skipped", "run_id": run.id, "conditions": condition_results}

    run = await _new_run(routine, trigger_type, context, spec, key, "running")
    results: list[dict] = []
    agent_run_id: int | None = None
    error: str | None = None
    for index, action in enumerate(spec.get("actions") or []):
        item = {"index": index, "type": action.get("type")}
        try:
            result = await _execute_action(routine, action)
            item.update({"status": "ok", "result": result})
            if action.get("type") == "agent" and result.get("agent_run_id"):
                agent_run_id = int(result["agent_run_id"])
            results.append(item)
        except Exception as exc:
            item.update({"status": "error", "error": str(exc)[:1000]})
            results.append(item)
            error = f"action {index} ({action.get('type')}) failed: {exc}"
            break

    if error:
        status = "partial" if any(item.get("status") == "ok" for item in results) else "failed"
    else:
        status = "succeeded"
    await _finish_run(
        run.id, routine, status=status, action_results=results,
        agent_run_id=agent_run_id, error=error,
    )
    return {
        "status": status,
        "run_id": run.id,
        "agent_run_id": agent_run_id,
        "actions": results,
        "error": error,
    }
