"""Datetime helpers for naive wall-clock DB columns.

``schedule_events`` / todo due dates are ``TIMESTAMP WITHOUT TIME ZONE`` and
store the user's local wall-clock time. Incoming ISO strings may carry ``Z`` or
``+08:00``; normalize them to local naive values so asyncpg never compares an
aware datetime with a naive column.
"""
from datetime import datetime


def parse_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def naive_local(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    return parse_datetime(value)
