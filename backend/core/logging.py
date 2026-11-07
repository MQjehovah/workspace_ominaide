"""Central logging setup and helpers.

The backend used ``print`` in many background tasks. This module gives every
runtime module a logger with request context and secret redaction.
"""

from __future__ import annotations

import json
import logging
import re
import sys

from core.config.settings import settings
from core.observability.context import get_trace_id, get_user_id

_SENSITIVE = re.compile(
    r"(?i)\b(token|access_token|refresh_token|password|authorization)"
    r"(\s*[=:]\s*)([^&\s,;]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]+")

_configured = False


def redact(text: str) -> str:
    text = _SENSITIVE.sub(lambda m: f"{m.group(1)}{m.group(2)}***", text or "")
    return _BEARER.sub("Bearer ***", text)


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_trace_id() or "-"
        record.user_id = get_user_id()
        return True


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
            "trace_id": getattr(record, "trace_id", "-"),
            "user_id": getattr(record, "user_id", None),
        }
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    level = getattr(logging, (settings.log_level or "INFO").upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(ContextFilter())
    if settings.log_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(RedactingFormatter(
            "%(asctime)s %(levelname)s trace_id=%(trace_id)s "
            "user_id=%(user_id)s %(name)s: %(message)s"
        ))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Let Uvicorn error logs use the same formatter and redaction. Access logs
    # are emitted by TraceMiddleware without query strings; disabling Uvicorn's
    # access logger also protects WebSocket URLs that carry tokens.
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(level)
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
    access.disabled = True
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
