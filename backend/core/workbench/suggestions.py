"""Workbench quick prompts.

The hourly daily-brief job generates ``prompts`` with the same LLM call as the
brief. This module only reads that snapshot and falls back to deterministic
suggestions when a user has not been warmed yet.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from core.cos.context import build_context
from core.logging import get_logger

log = get_logger(__name__)

_DEFAULT_SUGGESTIONS = [
    "整理收件箱",
    "看看今天的待办",
    "写本周周报",
]


def _short(value, limit: int = 14) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)] + "…"


def _fallback(context: dict) -> list[str]:
    out: list[str] = []
    for event in context.get("events", []):
        title = _short(event.get("title"), 12)
        if title:
            out.append(f"准备{title}")
    for todo in context.get("todos", []):
        title = _short(todo.get("title"), 12)
        if title:
            out.append(f"推进：{title}")
    mail = context.get("unread_mail", [])
    if mail:
        sender = _short(mail[0].get("from"), 10)
        out.append(f"回复{sender}的邮件" if sender else "整理未读邮件")
    if context.get("dingtalk"):
        out.append("查看钉钉未读消息")
    notes = context.get("recent_notes", [])
    if notes:
        out.append(f"继续编辑「{_short(notes[0].get('title'), 10)}」")
    projects = context.get("recent_projects", [])
    if projects:
        out.append(f"推进项目「{_short(projects[0].get('name'), 8)}」")
    if context.get("recent_files"):
        out.append("整理最近文件")
    out.extend(_DEFAULT_SUGGESTIONS)

    result: list[str] = []
    for item in out:
        if item and item not in result:
            result.append(item)
        if len(result) >= 3:
            break
    return result


async def workbench_suggestions(user_id: int, *, refresh: bool = False) -> dict:
    """Return cached brief prompts. ``refresh`` is kept for API compatibility."""
    from core.skills import brief_cache

    cached = await brief_cache.get_cached(user_id)
    if cached is not None:
        prompts = [str(item).strip() for item in (cached.get("prompts") or []) if str(item).strip()]
        if prompts:
            return {
                "suggestions": prompts[:3],
                "source": "brief",
                "generated_at": cached.get("generated_at"),
                "expires_at": (
                    datetime.fromisoformat(str(cached["generated_at"])) + timedelta(hours=1)
                ).isoformat(timespec="seconds") if cached.get("generated_at") else None,
            }

    context = await build_context(user_id)
    generated = datetime.now()
    return {
        "suggestions": _fallback(context),
        "source": "fallback",
        "generated_at": generated.isoformat(timespec="seconds"),
        "expires_at": (generated + timedelta(hours=1)).isoformat(timespec="seconds"),
    }
