from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from core.auth.dependencies import get_current_user
from core.database.session import async_session
from core.jobs.models import BackgroundJob
from core.observability.models import RequestTrace
from ai.bots.models import Approval, Run

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

_JOB_STATUSES = ("queued", "running", "done", "failed", "dead", "cancelled")
_RUN_STATUSES = ("queued", "running", "waiting_approval", "done", "failed", "cancelled")


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * fraction))
    return ordered[index]


def _naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone().replace(tzinfo=None)
    return value


@router.get("")
async def metrics(
    hours: int = Query(24, ge=1, le=168),
    user: dict = Depends(get_current_user),
):
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    since = now - timedelta(hours=hours - 1)
    user_id = user["id"]

    async with async_session() as db:
        rows = (
            await db.execute(
                select(
                    RequestTrace.kind,
                    RequestTrace.name,
                    RequestTrace.status,
                    RequestTrace.duration_ms,
                    RequestTrace.tokens_in,
                    RequestTrace.tokens_out,
                    RequestTrace.created_at,
                ).where(
                    RequestTrace.created_at >= since,
                    RequestTrace.user_id == user_id,
                )
            )
        ).all()
        slow = (
            await db.execute(
                select(
                    RequestTrace.kind,
                    RequestTrace.name,
                    RequestTrace.duration_ms,
                    RequestTrace.status,
                    RequestTrace.created_at,
                )
                .where(
                    RequestTrace.created_at >= since,
                    RequestTrace.user_id == user_id,
                )
                .order_by(RequestTrace.duration_ms.desc())
                .limit(20)
            )
        ).all()
        total = (
            await db.execute(
                select(func.count()).select_from(RequestTrace).where(
                    RequestTrace.created_at >= since,
                    RequestTrace.user_id == user_id,
                )
            )
        ).scalar() or 0
        token_rows = (
            await db.execute(
                select(
                    RequestTrace.name,
                    func.sum(RequestTrace.tokens_in),
                    func.sum(RequestTrace.tokens_out),
                    func.count(),
                )
                .where(
                    RequestTrace.created_at >= since,
                    RequestTrace.user_id == user_id,
                    RequestTrace.kind == "llm",
                    (RequestTrace.tokens_in + RequestTrace.tokens_out) > 0,
                )
                .group_by(RequestTrace.name)
                .order_by(
                    (
                        func.sum(RequestTrace.tokens_in)
                        + func.sum(RequestTrace.tokens_out)
                    ).desc()
                )
            )
        ).all()

        job_scope = or_(
            BackgroundJob.user_id == user_id,
            BackgroundJob.user_id.is_(None),
        )
        job_rows = (
            await db.execute(
                select(BackgroundJob.status, func.count())
                .where(BackgroundJob.created_at >= since, job_scope)
                .group_by(BackgroundJob.status)
            )
        ).all()
        jobs_active = (
            await db.execute(
                select(func.count()).select_from(BackgroundJob).where(
                    job_scope,
                    BackgroundJob.status.in_(("queued", "running")),
                )
            )
        ).scalar() or 0
        recent_failed_jobs = (
            await db.execute(
                select(
                    BackgroundJob.id,
                    BackgroundJob.kind,
                    BackgroundJob.status,
                    BackgroundJob.error,
                    BackgroundJob.updated_at,
                )
                .where(job_scope, BackgroundJob.status.in_(("failed", "dead")))
                .order_by(BackgroundJob.updated_at.desc())
                .limit(5)
            )
        ).all()

        run_rows = (
            await db.execute(
                select(Run.status, func.count())
                .where(Run.user_id == user_id, Run.created_at >= since)
                .group_by(Run.status)
            )
        ).all()
        runs_active = (
            await db.execute(
                select(func.count()).select_from(Run).where(
                    Run.user_id == user_id,
                    Run.status.in_(("queued", "running", "waiting_approval")),
                )
            )
        ).scalar() or 0
        recent_failed_runs = (
            await db.execute(
                select(Run.id, Run.input, Run.status, Run.error, Run.created_at)
                .where(Run.user_id == user_id, Run.status == "failed")
                .order_by(Run.created_at.desc())
                .limit(5)
            )
        ).all()
        approvals_pending = (
            await db.execute(
                select(func.count()).select_from(Approval).where(
                    Approval.user_id == user_id,
                    Approval.status == "pending",
                )
            )
        ).scalar() or 0

    groups: dict[str, dict] = {}
    name_groups: dict[tuple[str, str], dict] = {}
    timeline = [
        {
            "hour": (since + timedelta(hours=index)).isoformat(timespec="hours"),
            "requests": 0,
            "errors": 0,
            "llm_calls": 0,
            "tokens": 0,
        }
        for index in range(hours)
    ]
    all_durations: list[int] = []

    for kind, name, status, duration, tokens_in, tokens_out, created_at in rows:
        kind = kind or "request"
        duration = int(duration or 0)
        tokens_in = int(tokens_in or 0)
        tokens_out = int(tokens_out or 0)
        bucket = groups.setdefault(
            kind,
            {"count": 0, "errors": 0, "durations": [], "tokens_in": 0, "tokens_out": 0},
        )
        bucket["count"] += 1
        if status != "ok":
            bucket["errors"] += 1
        bucket["durations"].append(duration)
        bucket["tokens_in"] += tokens_in
        bucket["tokens_out"] += tokens_out
        all_durations.append(duration)

        key = (kind, name or kind)
        named = name_groups.setdefault(
            key,
            {"kind": kind, "name": name or kind, "count": 0, "errors": 0, "durations": [], "tokens": 0},
        )
        named["count"] += 1
        if status != "ok":
            named["errors"] += 1
        named["durations"].append(duration)
        named["tokens"] += tokens_in + tokens_out

        created_at = _naive(created_at)
        if created_at is not None:
            index = int((created_at - since).total_seconds() // 3600)
            if 0 <= index < len(timeline):
                slot = timeline[index]
                slot["requests"] += 1
                if status != "ok":
                    slot["errors"] += 1
                if kind == "llm":
                    slot["llm_calls"] += 1
                    slot["tokens"] += tokens_in + tokens_out

    summary = {
        key: {
            "count": value["count"],
            "errors": value["errors"],
            "error_rate": round(value["errors"] / value["count"], 4) if value["count"] else 0,
            "p50_ms": _percentile(value["durations"], 0.50),
            "p95_ms": _percentile(value["durations"], 0.95),
            "max_ms": max(value["durations"]) if value["durations"] else 0,
            "tokens_in": value["tokens_in"],
            "tokens_out": value["tokens_out"],
        }
        for key, value in groups.items()
    }

    top_names = [
        {
            "kind": value["kind"],
            "name": value["name"],
            "count": value["count"],
            "errors": value["errors"],
            "error_rate": round(value["errors"] / value["count"], 4) if value["count"] else 0,
            "p95_ms": _percentile(value["durations"], 0.95),
            "tokens": value["tokens"],
        }
        for value in sorted(name_groups.values(), key=lambda item: -item["count"])[:12]
    ]

    token_total_in = sum(int(row[1] or 0) for row in token_rows)
    token_total_out = sum(int(row[2] or 0) for row in token_rows)
    error_count = sum(value["errors"] for value in groups.values())

    job_counts = {status: 0 for status in _JOB_STATUSES}
    for status, count in job_rows:
        job_counts[str(status)] = int(count or 0)

    run_counts = {status: 0 for status in _RUN_STATUSES}
    for status, count in run_rows:
        run_counts[str(status)] = int(count or 0)

    return {
        "window_hours": hours,
        "total": total,
        "overview": {
            "requests": int(total),
            "errors": error_count,
            "error_rate": round(error_count / total, 4) if total else 0,
            "p50_ms": _percentile(all_durations, 0.50),
            "p95_ms": _percentile(all_durations, 0.95),
            "llm_calls": groups.get("llm", {}).get("count", 0),
            "tokens": token_total_in + token_total_out,
            "jobs_active": int(jobs_active),
            "agents_active": int(runs_active),
            "approvals_pending": int(approvals_pending),
        },
        "by_kind": summary,
        "top_names": top_names,
        "timeline": timeline,
        "tokens": {
            "input": token_total_in,
            "output": token_total_out,
            "total": token_total_in + token_total_out,
            "by_model": [
                {
                    "model": row[0] or "unknown",
                    "input": int(row[1] or 0),
                    "output": int(row[2] or 0),
                    "total": int(row[1] or 0) + int(row[2] or 0),
                    "calls": int(row[3] or 0),
                }
                for row in token_rows
            ],
        },
        "jobs": {
            **job_counts,
            "active": int(jobs_active),
            "recent_failed": [
                {
                    "id": row[0],
                    "kind": row[1],
                    "status": row[2],
                    "error": (row[3] or "")[:300] or None,
                    "updated_at": row[4].isoformat() if row[4] else None,
                }
                for row in recent_failed_jobs
            ],
        },
        "agents": {
            **run_counts,
            "active": int(runs_active),
            "approvals_pending": int(approvals_pending),
            "recent_failed": [
                {
                    "id": row[0],
                    "input": (row[1] or "")[:200],
                    "status": row[2],
                    "error": (row[3] or "")[:300] or None,
                    "created_at": row[4].isoformat() if row[4] else None,
                }
                for row in recent_failed_runs
            ],
        },
        "slowest": [
            {
                "kind": row[0],
                "name": row[1],
                "duration_ms": row[2],
                "status": row[3],
                "created_at": row[4].isoformat() if row[4] else None,
            }
            for row in slow
        ],
    }
