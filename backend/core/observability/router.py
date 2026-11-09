from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from core.auth.dependencies import get_current_user
from core.database.session import async_session
from core.observability.models import RequestTrace

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * fraction))
    return ordered[index]


@router.get("")
async def metrics(
    hours: int = Query(24, ge=1, le=168),
    user: dict = Depends(get_current_user),
):
    since = datetime.now() - timedelta(hours=hours)
    async with async_session() as db:
        rows = (
            await db.execute(
                select(
                    RequestTrace.kind,
                    RequestTrace.status,
                    RequestTrace.duration_ms,
                    RequestTrace.tokens_in,
                    RequestTrace.tokens_out,
                ).where(
                    RequestTrace.created_at >= since,
                    RequestTrace.user_id == user["id"],
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
                    RequestTrace.user_id == user["id"],
                )
                .order_by(RequestTrace.duration_ms.desc())
                .limit(20)
            )
        ).all()
        total = (
            await db.execute(
                select(func.count()).select_from(RequestTrace).where(
                    RequestTrace.created_at >= since,
                    RequestTrace.user_id == user["id"],
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
                    RequestTrace.user_id == user["id"],
                    RequestTrace.kind == "llm",
                )
                .group_by(RequestTrace.name)
                .order_by((func.sum(RequestTrace.tokens_in) + func.sum(RequestTrace.tokens_out)).desc())
            )
        ).all()

    groups: dict[str, dict] = {}
    for kind, status, duration, tokens_in, tokens_out in rows:
        bucket = groups.setdefault(
            kind or "request",
            {"count": 0, "errors": 0, "durations": []},
        )
        bucket["count"] += 1
        if status != "ok":
            bucket["errors"] += 1
        bucket["durations"].append(int(duration or 0))
        bucket["tokens_in"] = bucket.get("tokens_in", 0) + int(tokens_in or 0)
        bucket["tokens_out"] = bucket.get("tokens_out", 0) + int(tokens_out or 0)

    token_total_in = sum(int(row[1] or 0) for row in token_rows)
    token_total_out = sum(int(row[2] or 0) for row in token_rows)

    summary = {
        key: {
            "count": value["count"],
            "errors": value["errors"],
            "error_rate": round(
                value["errors"] / value["count"], 4
            ) if value["count"] else 0,
            "p50_ms": _percentile(value["durations"], 0.50),
            "p95_ms": _percentile(value["durations"], 0.95),
            "max_ms": max(value["durations"]) if value["durations"] else 0,
            "tokens_in": value.get("tokens_in", 0),
            "tokens_out": value.get("tokens_out", 0),
        }
        for key, value in groups.items()
    }
    return {
        "window_hours": hours,
        "total": total,
        "by_kind": summary,
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
