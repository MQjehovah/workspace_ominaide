from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware

from core.logging import get_logger
from core.observability.context import set_trace_id, set_user_id
from core.observability.recorder import record_trace

log = get_logger("http")


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        trace_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        set_trace_id(trace_id)
        set_user_id(None)
        started = time.monotonic()
        status_code = 500
        error: str | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = trace_id
            return response
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            duration = int((time.monotonic() - started) * 1000)
            if request.url.path not in {"/health"}:
                log.info(
                    "%s %s -> %s %dms",
                    request.method, request.url.path, status_code, duration,
                )
                record_trace(
                    trace_id=trace_id,
                    kind="request",
                    name=f"{request.method} {request.url.path}",
                    method=request.method,
                    status="ok" if status_code < 500 else "error",
                    status_code=status_code,
                    duration_ms=duration,
                    error=error,
                )
