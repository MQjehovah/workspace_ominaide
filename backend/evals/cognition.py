"""Golden-path checks and metrics for the cognition layer.

Usage:
    python -m evals.cognition --user-id 1
    python -m evals.cognition --user-id 1 --json

The report is persisted to ``data/evals/cognition.json`` and exposed by
``GET /api/cognition/evals`` for the metrics dashboard.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from ai.bots.registry import get_active_bot
from ai.cognition.agent_profiles import get_profile, scoped_tools
from ai.cognition.authorization import (
    authorize,
    consume_grant,
    create_grant,
)
from ai.cognition.capabilities import describe_capability
from ai.cognition.goals import (
    create_goal,
    create_task,
    list_tasks,
    ready_tasks,
)
from ai.cognition.verifier import verify_task
from ai.cognition.handoff import handoff
from ai.cognition.interruptions import in_quiet_hours
from ai.cognition.planner import plan_goal
from ai.cognition.proposals import (
    act_proposal,
    create_proposal,
    get_proposal,
)
from ai.cognition.situation import get_situation, situation_prompt
from ai.cognition.workspace import (
    add_item,
    delete_item,
    ensure_workspace,
    export_zip,
    update_item,
)
from ai.memory.curator import curate_user

REPORT_PATH = Path("data/evals/cognition.json")


def _report_meta() -> dict:
    return {"generated_at": datetime.now().isoformat(timespec="seconds")}


def load_report() -> dict:
    try:
        return json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"generated_at": None, "cases": [], "metrics": {}}


def _save_report(report: dict) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _metrics(cases: list[dict]) -> dict:
    total = len(cases)
    passed = sum(1 for case in cases if case["ok"])
    durations = sorted(case["duration_ms"] for case in cases)
    p95 = durations[min(len(durations) - 1, int(len(durations) * 0.95))] if durations else 0
    by_category: dict[str, dict] = {}
    for case in cases:
        bucket = by_category.setdefault(
            case["category"], {"total": 0, "passed": 0}
        )
        bucket["total"] += 1
        bucket["passed"] += 1 if case["ok"] else 0
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "avg_ms": round(sum(durations) / total, 1) if total else 0.0,
        "p95_ms": round(float(p95), 1) if durations else 0.0,
        "by_category": by_category,
    }


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------


async def _situation(user_id: int) -> tuple[bool, str]:
    snapshot = await get_situation(user_id, force=True)
    ok = bool(snapshot.get("generated_at")) and "signals" in snapshot
    return ok, "snapshot has generated_at and signals"


async def _situation_prompt(user_id: int) -> tuple[bool, str]:
    text = await situation_prompt(user_id)
    return isinstance(text, str), f"prompt chars={len(text)}"


async def _proposal_create(user_id: int) -> tuple[bool, str]:
    row = await create_proposal(
        user_id, kind="follow_up", title="评测：整理周报素材", channel="now"
    )
    return bool(row.id), f"proposal id={row.id}"


async def _proposal_dedupe(user_id: int) -> tuple[bool, str]:
    first = await create_proposal(
        user_id, kind="follow_up", title="评测：跟进预算确认", channel="now"
    )
    second = await create_proposal(
        user_id, kind="follow_up", title="评测：跟进预算的确认。", channel="now"
    )
    return first.id == second.id, f"ids={first.id},{second.id}"


async def _proposal_accept_goal(user_id: int) -> tuple[bool, str]:
    row = await create_proposal(
        user_id,
        kind="follow_up",
        title="评测：接受后建目标",
        channel="now",
        actions=[{
            "key": "create_goal",
            "label": "接受",
            "kind": "create_goal",
            "payload": {},
        }],
    )
    result = await act_proposal(user_id, row.id, action="accept")
    return bool(result and result.get("goal_id")), f"result={result}"


async def _proposal_snooze(user_id: int) -> tuple[bool, str]:
    row = await create_proposal(
        user_id, kind="follow_up", title="评测：稍后提醒", channel="now"
    )
    result = await act_proposal(user_id, row.id, action="snooze", snooze_minutes=5)
    fresh = await get_proposal(user_id, row.id)
    ok = bool(result and fresh and fresh["status"] == "snoozed")
    return ok, f"status={fresh['status'] if fresh else None}"


async def _proposal_dismiss(user_id: int) -> tuple[bool, str]:
    row = await create_proposal(
        user_id, kind="follow_up", title="评测：忽略提案", channel="now"
    )
    await act_proposal(user_id, row.id, action="dismiss")
    fresh = await get_proposal(user_id, row.id)
    return bool(fresh and fresh["status"] == "dismissed"), f"status={fresh['status'] if fresh else None}"


async def _goal_create(user_id: int) -> tuple[bool, str]:
    goal = await create_goal(user_id, title="评测：准备评审", description="评测用例")
    return bool(goal.id and goal.workspace_id), f"goal={goal.id} workspace={goal.workspace_id}"


async def _goal_plan(user_id: int) -> tuple[bool, str]:
    goal = await create_goal(user_id, title="评测：规划目标", description="评测用例")
    await plan_goal(user_id, goal.id)
    tasks = await list_tasks(user_id, goal.id)
    return bool(tasks), f"tasks={len(tasks)}"


async def _task_dependency(user_id: int) -> tuple[bool, str]:
    goal = await create_goal(user_id, title="评测：任务依赖")
    first = await create_task(user_id, goal.id, title="第一步", sort_order=0)
    second = await create_task(
        user_id, goal.id, title="第二步", sort_order=1,
        depends_on=[first.id] if first else [],
    )
    ready = await ready_tasks(user_id, goal.id)
    ok = bool(second and [t["id"] for t in ready] == [first.id])
    return ok, f"ready={[t['id'] for t in ready]}"


async def _task_verify(user_id: int) -> tuple[bool, str]:
    goal = await create_goal(user_id, title="评测：验收任务")
    task = await create_task(user_id, goal.id, title="待验收", acceptance=["有结论"])
    result = await verify_task(user_id, task.id)
    return bool(result and result.get("passed") is False), f"result={result}"


async def _workspace_ensure(user_id: int) -> tuple[bool, str]:
    goal = await create_goal(user_id, title="评测：工作区幂等")
    first = await ensure_workspace(user_id, goal.id)
    second = await ensure_workspace(user_id, goal.id)
    return bool(first and second and first.id == second.id), f"id={first.id if first else None}"


async def _workspace_item(user_id: int) -> tuple[bool, str]:
    goal = await create_goal(user_id, title="评测：工作区条目")
    workspace = await ensure_workspace(user_id, goal.id)
    item = await add_item(
        user_id, workspace.id, type="comment", content={"text": "初稿"}
    )
    updated = await update_item(
        user_id, workspace.id, item["id"], content={"text": "定稿"}
    )
    deleted = await delete_item(user_id, workspace.id, item["id"])
    ok = bool(updated and updated["content"]["text"] == "定稿" and deleted)
    return ok, f"item={item['id']}"


async def _workspace_export(user_id: int) -> tuple[bool, str]:
    goal = await create_goal(user_id, title="评测：工作区导出")
    workspace = await ensure_workspace(user_id, goal.id)
    await add_item(user_id, workspace.id, type="fact", content={"text": "导出内容"})
    data = await export_zip(user_id, workspace.id)
    return bool(data and data.startswith(b"PK")), f"bytes={len(data or b'')}"


async def _clear_grants(user_id: int, key: str = "send_email") -> None:
    from sqlalchemy import delete

    from ai.cognition.models import CapabilityGrant
    from core.database.session import async_session

    async with async_session() as db:
        await db.execute(delete(CapabilityGrant).where(
            CapabilityGrant.user_id == user_id,
            CapabilityGrant.capability_key == key,
        ))
        await db.commit()


async def _grant_allow(user_id: int) -> tuple[bool, str]:
    bot = await get_active_bot(user_id)
    await _clear_grants(user_id)
    await create_grant(user_id, "send_email", bot_id=bot.id)
    result = await authorize(
        user_id, "send_email", {"to": ["eval@example.com"]}, bot=bot
    )
    return result.decision == "allow", f"decision={result.decision}"


async def _grant_deny(user_id: int) -> tuple[bool, str]:
    bot = await get_active_bot(user_id)
    await _clear_grants(user_id)
    await create_grant(user_id, "send_email", decision="deny", bot_id=bot.id)
    result = await authorize(
        user_id, "send_email", {"to": ["eval@example.com"]}, bot=bot
    )
    return result.decision == "deny", f"decision={result.decision}"


async def _grant_once(user_id: int) -> tuple[bool, str]:
    bot = await get_active_bot(user_id)
    await _clear_grants(user_id)
    grant = await create_grant(user_id, "send_email", scope="once", bot_id=bot.id)
    first = await authorize(
        user_id, "send_email", {"to": ["eval@example.com"]}, bot=bot
    )
    await consume_grant(grant.id)
    second = await authorize(
        user_id, "send_email", {"to": ["eval@example.com"]}, bot=bot
    )
    ok = first.decision == "allow" and second.decision == "require_approval"
    return ok, f"{first.decision}->{second.decision}"


async def _grant_session_scope(user_id: int) -> tuple[bool, str]:
    bot = await get_active_bot(user_id)
    await _clear_grants(user_id)
    await create_grant(
        user_id, "send_email", scope="session", session_id="eval-s1", bot_id=bot.id
    )
    inside = await authorize(
        user_id, "send_email", {"to": ["eval@example.com"]},
        bot=bot, session_id="eval-s1",
    )
    outside = await authorize(
        user_id, "send_email", {"to": ["eval@example.com"]},
        bot=bot, session_id="eval-s2",
    )
    ok = inside.decision == "allow" and outside.decision == "require_approval"
    return ok, f"inside={inside.decision} outside={outside.decision}"


async def _profile_readonly_deny(user_id: int) -> tuple[bool, str]:
    bot = await get_active_bot(user_id)
    result = await authorize(
        user_id, "send_email", {"to": ["eval@example.com"]},
        bot=bot, agent_profile_key="planner",
    )
    return result.decision == "deny", f"decision={result.decision}"


async def _profile_tool_scope(user_id: int) -> tuple[bool, str]:
    bot = await get_active_bot(user_id)
    allowed = scoped_tools(bot, get_profile("planner")) or []
    return "send_email" not in allowed, f"tools={len(allowed)}"


async def _interruption_quiet_hours(user_id: int) -> tuple[bool, str]:
    moment = datetime.now().replace(hour=23, minute=30)
    quiet = in_quiet_hours(moment, "22:00-08:00")
    open_hour = in_quiet_hours(moment.replace(hour=12), "22:00-08:00")
    return quiet and not open_hour, f"quiet={quiet} noon={open_hour}"


async def _memory_curate(user_id: int) -> tuple[bool, str]:
    result = await curate_user(user_id)
    return {"expired", "updated"}.issubset(result.keys()), f"result={result}"


async def _handoff_offline(user_id: int) -> tuple[bool, str]:
    result = await handoff(user_id, machine_id="__eval_missing__", note="评测")
    return result.get("sent") is False, f"result={result}"


async def _capability_risk(user_id: int) -> tuple[bool, str]:
    risk = describe_capability("send_email").risk
    return bool(risk), f"risk={risk}"


async def _entity_resolution(user_id: int) -> tuple[bool, str]:
    from ai.entities.models import EntityAlias
    from ai.entities.service import resolve_entity
    from core.database.session import async_session

    async with async_session() as db:
        person = await resolve_entity(
            db, user_id, "person", "评测张三", alias_type="name"
        )
        db.add(EntityAlias(
            user_id=user_id,
            entity_id=person.id,
            alias="eval-zhangsan@example.com",
            alias_type="email",
        ))
        await db.flush()
        same = await resolve_entity(
            db, user_id, "person", "eval-zhangsan@example.com", alias_type="email"
        )
        await db.commit()
    return person.id == same.id, f"entity_id={person.id}"


async def _memory_situation_proposal(user_id: int) -> tuple[bool, str]:
    from plugins.schedule.backend.models import Event
    from ai.memory.models import MemoryRecord
    from core.database.session import async_session
    from ai.cognition.miner import mine_user

    async with async_session() as db:
        db.add(Event(
            user_id=user_id,
            title="和评测张三开报价评审会",
            start_time=datetime.now() + timedelta(hours=2),
        ))
        db.add(MemoryRecord(
            user_id=user_id,
            kind="commitment",
            content="评测：会前把报价发给评测张三",
            normalized="评测：会前把报价发给评测张三",
            confidence=90,
            data={
                "person": "评测张三",
                "state": "open",
                "quote": "我周五前把报价发你",
            },
        ))
        await db.commit()
    result = await mine_user(user_id)
    return result["created"] >= 1, f"result={result}"


async def _resolved_memory_closes_proposal(user_id: int) -> tuple[bool, str]:
    from ai.memory.models import MemoryRecord
    from core.database.session import async_session
    from ai.cognition.miner import mine_user

    async with async_session() as db:
        row = MemoryRecord(
            user_id=user_id,
            kind="commitment",
            content="评测：已解决的承诺",
            normalized="评测：已解决的承诺",
            confidence=90,
            data={
                "person": "评测张三",
                "state": "resolved",
                "quote": "已经完成",
            },
        )
        db.add(row)
        await db.commit()
    result = await mine_user(user_id)
    return result["created"] == 0, f"result={result}"


CASES = [
    ("situation_snapshot", "situation", _situation),
    ("situation_prompt", "situation", _situation_prompt),
    ("proposal_create", "proposal", _proposal_create),
    ("proposal_semantic_dedupe", "proposal", _proposal_dedupe),
    ("proposal_accept_goal", "proposal", _proposal_accept_goal),
    ("proposal_snooze", "proposal", _proposal_snooze),
    ("proposal_dismiss", "proposal", _proposal_dismiss),
    ("goal_create", "goal", _goal_create),
    ("goal_plan", "goal", _goal_plan),
    ("task_dependency", "goal", _task_dependency),
    ("task_verify", "goal", _task_verify),
    ("workspace_ensure", "workspace", _workspace_ensure),
    ("workspace_item_crud", "workspace", _workspace_item),
    ("workspace_export", "workspace", _workspace_export),
    ("grant_allow", "authorization", _grant_allow),
    ("grant_deny", "authorization", _grant_deny),
    ("grant_once", "authorization", _grant_once),
    ("grant_session_scope", "authorization", _grant_session_scope),
    ("profile_readonly_deny", "agent", _profile_readonly_deny),
    ("profile_tool_scope", "agent", _profile_tool_scope),
    ("interruption_quiet_hours", "interruption", _interruption_quiet_hours),
    ("memory_curate", "memory", _memory_curate),
    ("handoff_offline", "handoff", _handoff_offline),
    ("capability_risk", "capability", _capability_risk),
    ("entity_resolution", "entity", _entity_resolution),
    ("memory_situation_proposal", "mining", _memory_situation_proposal),
    (
        "resolved_memory_closes_proposal",
        "mining",
        _resolved_memory_closes_proposal,
    ),
]


async def run(user_id: int) -> int:
    results: list[dict] = []
    for name, category, case in CASES:
        started = time.monotonic()
        try:
            ok, detail = await case(user_id)
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        duration = round((time.monotonic() - started) * 1000, 1)
        results.append({
            "name": name,
            "category": category,
            "ok": bool(ok),
            "detail": detail,
            "duration_ms": duration,
        })
        print(f"[{'PASS' if ok else 'FAIL'}] {category}/{name} ({duration}ms) {detail}")

    metrics = _metrics(results)
    report = {**_report_meta(), "user_id": user_id, "cases": results, "metrics": metrics}
    _save_report(report)

    print(
        f"\n{metrics['passed']}/{metrics['total']} cases passed "
        f"({metrics['pass_rate'] * 100:.1f}%), "
        f"avg {metrics['avg_ms']}ms, p95 {metrics['p95_ms']}ms"
    )
    return 0 if metrics["failed"] == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    code = asyncio.run(run(args.user_id))
    if args.json:
        print(json.dumps(load_report(), ensure_ascii=False, indent=2, default=str))
    raise SystemExit(code)
