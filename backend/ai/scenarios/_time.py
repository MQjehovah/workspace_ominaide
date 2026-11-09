"""Small date helpers shared by AI scenarios."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min)
    return start, start + timedelta(days=1)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        from core.timeutil import parse_datetime

        return parse_datetime(value)
    except Exception:
        return None
