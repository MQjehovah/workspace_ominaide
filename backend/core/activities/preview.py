"""Compact, redacted previews of tool arguments for activity records.

The activity stream is fed back to the agent as context, so it should carry
enough detail to explain what happened without storing huge or sensitive
payloads. Values are truncated and credential-looking keys are masked.
"""

from __future__ import annotations

from typing import Any

_SENSITIVE_MARKERS = (
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "authorization", "cookie", "credential", "private_key", "access_key",
)


def _preview_value(value: Any, depth: int = 0) -> Any:
    if depth >= 3:
        return "…"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:240] + ("…" if len(value) > 240 else "")
    if isinstance(value, dict):
        return {
            str(key): _preview_value(item, depth + 1)
            for key, item in list(value.items())[:12]
        }
    if isinstance(value, (list, tuple)):
        return [_preview_value(item, depth + 1) for item in list(value)[:8]]
    return str(value)[:240]


def preview_arguments(arguments: Any) -> dict:
    """Return a bounded, redacted preview of a tool argument mapping."""
    if not isinstance(arguments, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in list(arguments.items())[:20]:
        name = str(key)
        if any(marker in name.lower() for marker in _SENSITIVE_MARKERS):
            out[name] = "***"
        else:
            out[name] = _preview_value(value)
    return out
