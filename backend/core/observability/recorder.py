from __future__ import annotations

from core.logging import get_logger
log = get_logger(__name__)

import asyncio
import time
from contextlib import asynccontextmanager

from core.observability.context import get_trace_id, get_user_id
from core.observability.models import RequestTrace


async def _write_trace(
    *,
    trace_id: str,
    user_id: int | None,
    kind: str,
    name: str,
    method: str | None,
    status: str,
    status_code: int | None,
    duration_ms: int,
    error: str | None,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> None:
    try:
        from core.database.session import async_session

        async with async_session() as db:
            db.add(
                RequestTrace(
                    trace_id=trace_id,
                    user_id=user_id,
                    kind=kind,
                    name=name[:300],
                    method=method,
                    status=status,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    tokens_in=int(tokens_in or 0),
                    tokens_out=int(tokens_out or 0),
                    error=(error or "")[:2000] or None,
                )
            )
            await db.commit()
    except Exception as exc:
        log.warning(f"[observability] trace write error: {exc}")


def record_trace(
    *,
    trace_id: str,
    kind: str,
    name: str,
    duration_ms: int,
    status: str = "ok",
    status_code: int | None = None,
    method: str | None = None,
    error: str | None = None,
    user_id: int | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> None:
    asyncio.create_task(
        _write_trace(
            trace_id=trace_id,
            user_id=user_id if user_id is not None else get_user_id(),
            kind=kind,
            name=name,
            method=method,
            status=status,
            status_code=status_code,
            duration_ms=duration_ms,
            error=error,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
    )


class TraceSpan:
    def __init__(self) -> None:
        self.tokens_in = 0
        self.tokens_out = 0

    def add_usage(self, usage) -> None:
        if usage is None:
            return
        self.tokens_in += int(getattr(usage, "prompt_tokens", 0) or 0)
        self.tokens_out += int(getattr(usage, "completion_tokens", 0) or 0)


@asynccontextmanager
async def trace_span(kind: str, name: str):
    """Measure an external call (MCP / LLM / ASR / sync) with the request trace."""
    started = time.monotonic()
    status = "ok"
    error: str | None = None
    span = TraceSpan()
    try:
        yield span
    except Exception as exc:
        status = "error"
        error = str(exc)
        raise
    finally:
        record_trace(
            trace_id=get_trace_id() or "background",
            kind=kind,
            name=name,
            duration_ms=int((time.monotonic() - started) * 1000),
            status=status,
            error=error,
            tokens_in=span.tokens_in,
            tokens_out=span.tokens_out,
        )
