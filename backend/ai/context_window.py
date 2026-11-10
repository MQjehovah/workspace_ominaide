"""Shared context-window compression for chat and coding agents.

Both agent loops call :func:`compact_context` before each LLM request. The
compressor keeps system instructions and the most recent user turns, summarizes
older turns with the same model, and falls back to a deterministic summary if
the summarization call fails.

Character counts are used deliberately: they are model-agnostic and cheap.
"""

from __future__ import annotations

import json
import logging

from core.config.settings import settings

log = logging.getLogger("uvicorn")

MAX_TRANSCRIPT_CHARS = 30_000
MAX_TRANSCRIPT_MESSAGE_CHARS = 4_000


def estimate_chars(messages: list[dict]) -> int:
    total = 0
    for message in messages or []:
        total += len(str(message.get("content") or ""))
        total += len(json.dumps(message.get("tool_calls") or [], ensure_ascii=False))
        total += 32
    return total


def _truncate_tool_content(messages: list[dict], limit: int) -> list[dict]:
    result = []
    for message in messages:
        if message.get("role") == "tool" and isinstance(message.get("content"), str):
            content = message["content"]
            if len(content) > limit:
                message = {
                    **message,
                    "content": content[:limit] + "\n...[工具输出已截断]",
                }
        result.append(message)
    return result


def _fallback_summary(old: list[dict], limit: int) -> str:
    user_requests = []
    for message in old:
        if message.get("role") != "user":
            continue
        text = str(message.get("content") or "").strip().replace("\n", " ")
        if text:
            user_requests.append(text[:400])
    tail = "；".join(user_requests[-6:])
    note = f"较早的 {len(old)} 条消息已压缩"
    return (note + ("。早期用户请求：" + tail if tail else "。"))[:limit]


async def _summarize(old: list[dict], client, model: str, limit: int) -> str:
    lines = []
    for message in old:
        role = str(message.get("role") or "message")
        content = str(message.get("content") or "")
        if message.get("tool_calls"):
            names = [
                str((call.get("function") or {}).get("name") or "")
                for call in message.get("tool_calls") or []
            ]
            names = [name for name in names if name]
            if names:
                content = (content + "\n" if content else "") + "工具调用：" + ", ".join(names)
        if len(content) > MAX_TRANSCRIPT_MESSAGE_CHARS:
            content = content[:MAX_TRANSCRIPT_MESSAGE_CHARS] + "\n...[截断]"
        lines.append(f"{role.upper()}: {content}")
    transcript = "\n".join(lines)[-MAX_TRANSCRIPT_CHARS:]
    from ai.llm.usage import tracked_create

    response = await tracked_create(
        client,
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "你负责压缩 Agent 对话上下文。输出简洁摘要，必须保留："
                    "用户目标、已确认的决策、修改过的文件、执行过的命令与测试结果、"
                    "未解决的错误、下一步。不要编造未发生的内容。"
                ),
            },
            {"role": "user", "content": transcript},
        ],
        temperature=0.1,
        max_tokens=800,
    )
    return str(response.choices[0].message.content or "")[:limit]


async def compact_context(
    messages: list[dict],
    *,
    client=None,
    model: str | None = None,
    threshold_chars: int | None = None,
    keep_recent_turns: int | None = None,
    tool_result_max_chars: int | None = None,
    summary_max_chars: int | None = None,
) -> list[dict]:
    """Return a compacted copy of ``messages`` when it exceeds the budget."""
    if not settings.context_compress_enabled or not messages:
        return messages

    threshold = int(threshold_chars or settings.context_compress_threshold_chars or 60000)
    keep_turns = max(int(keep_recent_turns or settings.context_keep_recent_turns or 6), 1)
    tool_limit = max(int(tool_result_max_chars or settings.context_tool_result_max_chars or 8000), 500)
    summary_limit = max(int(summary_max_chars or settings.context_summary_max_chars or 4000), 500)

    if estimate_chars(messages) <= threshold:
        return messages

    system_messages = [m for m in messages if m.get("role") == "system"]
    conversation = [m for m in messages if m.get("role") != "system"]
    conversation = _truncate_tool_content(conversation, tool_limit)

    if estimate_chars(system_messages + conversation) <= threshold:
        return system_messages + conversation

    user_indices = [index for index, message in enumerate(conversation) if message.get("role") == "user"]
    keep = min(keep_turns, len(user_indices)) if user_indices else 0
    start = 0
    if keep:
        start = user_indices[-keep] if len(user_indices) > keep else 0
        # If there is no older history to summarize but we are still over
        # budget, progressively keep fewer recent turns.
        while (
            start == 0
            and keep > 1
            and estimate_chars(system_messages + conversation) > threshold
        ):
            keep -= 1
            start = user_indices[-keep]
    old = conversation[:start]
    recent = conversation[start:]

    summary_message = None
    if old:
        summary = ""
        if client is not None and model:
            try:
                summary = await _summarize(old, client, model, summary_limit)
            except Exception as exc:
                log.warning("[context] summarization failed: %s", exc)
        if not summary:
            summary = _fallback_summary(old, summary_limit)
        summary_message = {
            "role": "system",
            "content": "【较早上下文摘要】\n" + summary,
        }

    compacted = system_messages + ([summary_message] if summary_message else []) + recent
    if estimate_chars(compacted) > threshold:
        log.warning(
            "[context] still above budget after compression: %s > %s",
            estimate_chars(compacted),
            threshold,
        )
    return compacted
