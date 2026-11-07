from __future__ import annotations

import contextvars

trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trace_id", default=None
)
user_id_var: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "trace_user_id", default=None
)

_request_started_at: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "request_started_at", default=None
)


def set_trace_id(value: str | None) -> None:
    trace_id_var.set(value)


def get_trace_id() -> str | None:
    return trace_id_var.get()


def set_user_id(value: int | None) -> None:
    user_id_var.set(value)


def get_user_id() -> int | None:
    return user_id_var.get()
