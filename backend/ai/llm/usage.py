"""OpenAI call wrapper that records LLM token usage into request traces."""

from __future__ import annotations

import time

from core.observability.context import get_trace_id
from core.observability.recorder import record_trace


def _token_pair(usage) -> tuple[int, int]:
    if usage is None:
        return 0, 0
    prompt = getattr(usage, "prompt_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    if prompt is None and isinstance(usage, dict):
        prompt = usage.get("prompt_tokens")
        completion = usage.get("completion_tokens")
    return int(prompt or 0), int(completion or 0)


def record_chat_usage(model: str | None, usage, *, duration_ms: int = 0) -> None:
    tokens_in, tokens_out = _token_pair(usage)
    if tokens_in <= 0 and tokens_out <= 0:
        return
    record_trace(
        trace_id=get_trace_id() or "background",
        kind="llm",
        name=model or "llm",
        duration_ms=duration_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )


async def tracked_create(client, **kwargs):
    """Call ``chat.completions.create`` and record tokens for non-stream calls."""
    started = time.monotonic()
    response = await client.chat.completions.create(**kwargs)
    if not kwargs.get("stream"):
        record_chat_usage(
            kwargs.get("model"),
            getattr(response, "usage", None),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    return response
