"""JSON responses that make UTC timestamps explicit.

Most timestamp columns are ``TIMESTAMP WITHOUT TIME ZONE`` holding UTC, while a
few (schedule start/end, todo due dates, bot ``next_run_at``) intentionally hold
local wall-clock time. The API therefore used to emit both kinds as identical
naive ISO strings, forcing every client to guess.

This response class appends ``Z`` to values of known UTC keys only, leaving
local wall-clock fields untouched. It runs on FastAPI JSONResponse content
(before JSON encoding), so streaming/SSE responses are unaffected.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from fastapi.responses import JSONResponse

# Wall-clock fields: never converted.
_LOCAL_KEYS = {
    "next_run_at",
    "start_time",
    "end_time",
    "start",
    "end",
    "due_date",
    "due",
    "deadline",
    "time",
    "date",
    "day",
}

# UTC fields that do not follow the ``*_at`` convention.
_EXTRA_UTC_KEYS = {
    "last_analysis",
    "published",
    "published_at",
}

_NAIVE_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$")


def _is_utc_key(key: str) -> bool:
    if key in _LOCAL_KEYS:
        return False
    return key.endswith("_at") or key in _EXTRA_UTC_KEYS


def _mark_utc(value: str) -> str:
    if not _NAIVE_ISO.match(value):
        return value
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    if parsed.tzinfo is not None:
        return value
    return f"{value}Z"


def _walk(content: Any) -> None:
    if isinstance(content, dict):
        for key, value in content.items():
            if isinstance(value, str) and _is_utc_key(str(key)):
                content[key] = _mark_utc(value)
            elif isinstance(value, (dict, list)):
                _walk(value)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, (dict, list)):
                _walk(item)


class UTCJSONResponse(JSONResponse):
    """JSONResponse that marks naive UTC datetimes with a trailing ``Z``."""

    def render(self, content: Any) -> bytes:
        if isinstance(content, (dict, list)):
            _walk(content)
        return super().render(content)
