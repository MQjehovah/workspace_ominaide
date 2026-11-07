"""AI-generated workbench prompt suggestions.

The workbench shows three short actions the user is likely to need next. They
are inferred from the same deterministic signals the inbox already uses, then
optionally polished by the active bot. Results are cached for one hour so the
workbench stays fast and the suggestions only change on the requested cadence.
"""

from __future__ import annotations

from core.logging import get_logger
log = get_logger(__name__)

import json
import time
from datetime import datetime, timedelta

from sqlalchemy import select

from core.config.settings import settings
from core.cos import collectors
from core.cos.service import _llm_json
from core.database.session import async_session

_TTL_SECONDS = 3600.0
_CACHE: dict[int, tuple[float, dict]] = {}

_DEFAULT_SUGGESTIONS = [
    "整理收件箱",
    "看看今天的待办",
    "写本周周报",
]

_SYSTEM = (
    "你是用户的私人助理。根据给定的日程、待办、未读邮件、钉钉最近会话、"
    "最近笔记/文件/项目，推断用户接下来最可能需要处理的 3 件事。"
    '只输出 JSON：{"suggestions":["...","...","..."]}。'
    "每条 6-14 个中文字符，动词开头、可直接执行；不要编号、不要解释。"
    "优先即将开始的日程、逾期或今天到期的待办、需要回复的未读消息；"
    "其次最近编辑的笔记或项目。不要编造数据里没有的事情。"
)


def _short(value, limit: int = 14) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)] + "…"


def _parse(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except Exception:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


async def _recent_notes(user_id: int) -> list[dict]:
    from plugins.notes.backend.models import PluginNote

    async with async_session() as db:
        rows = (
            await db.execute(
                select(PluginNote)
                .where(
                    PluginNote.user_id == user_id,
                    PluginNote.is_folder == 0,
                )
                .order_by(PluginNote.updated_at.desc())
                .limit(3)
            )
        ).scalars().all()
    return [
        {
            "title": row.title,
            "updated": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]


async def _recent_files(user_id: int) -> list[dict]:
    from plugins.files.backend.models import File

    async with async_session() as db:
        rows = (
            await db.execute(
                select(File)
                .where(
                    File.user_id == user_id,
                    File.is_folder == False,  # noqa: E712
                    File.status == "active",
                )
                .order_by(File.created_at.desc())
                .limit(3)
            )
        ).scalars().all()
    return [
        {
            "name": row.original_name,
            "created": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


async def _recent_projects(user_id: int) -> list[dict]:
    from plugins.projects.backend.models import Project

    async with async_session() as db:
        rows = (
            await db.execute(
                select(Project)
                .where(Project.user_id == user_id)
                .order_by(Project.updated_at.desc())
                .limit(3)
            )
        ).scalars().all()
    return [
        {
            "name": row.name,
            "updated": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]


async def _context(user_id: int) -> dict:
    now = datetime.now()
    events = await collectors.schedule_items(
        user_id,
        start=now - timedelta(minutes=30),
        end=now + timedelta(days=2),
        limit=6,
    )
    todos = await collectors.todo_items(user_id, limit=8)
    mail = await collectors.mail_items(
        user_id,
        since=now - timedelta(days=3),
        limit=6,
        unread_only=True,
    )
    dingtalk, _ = await collectors.dingtalk_items(user_id, limit=5)

    return {
        "now": now.isoformat(timespec="minutes"),
        "events": [
            {"time": item.get("time"), "title": item.get("title")}
            for item in events
        ],
        "todos": [
            {
                "title": item.get("title"),
                "due": (item.get("meta") or {}).get("due"),
                "priority": item.get("priority"),
            }
            for item in todos
        ],
        "unread_mail": [
            {"from": item.get("from"), "subject": item.get("title")}
            for item in mail
        ],
        "recent_dingtalk": [
            {"conversation": item.get("title"), "text": item.get("summary")}
            for item in dingtalk
        ],
        "recent_notes": await _recent_notes(user_id),
        "recent_files": await _recent_files(user_id),
        "recent_projects": await _recent_projects(user_id),
    }


def _fallback(context: dict) -> list[str]:
    now = datetime.now()
    out: list[str] = []

    for event in context["events"]:
        at = _parse(event.get("time"))
        title = _short(event.get("title"), 12)
        if at is not None and title:
            out.append(f"准备 {at.hour:02d}:{at.minute:02d} 的{title}")

    for todo in context["todos"]:
        title = _short(todo.get("title"), 12)
        if not title:
            continue
        due = _parse(todo.get("due"))
        if due is not None and due < now:
            out.append(f"处理逾期：{title}")
        else:
            out.append(f"推进：{title}")

    mail = context["unread_mail"]
    if mail:
        sender = _short(mail[0].get("from"), 10)
        out.append(f"回复{sender}的邮件" if sender else "整理未读邮件")

    if context["recent_dingtalk"]:
        out.append("查看钉钉未读消息")

    if context["recent_notes"]:
        out.append(f"继续编辑「{_short(context['recent_notes'][0].get('title'), 10)}」")

    if context["recent_projects"]:
        out.append(f"推进项目「{_short(context['recent_projects'][0].get('name'), 8)}」")

    if context["recent_files"]:
        out.append("整理最近文件")

    for item in _DEFAULT_SUGGESTIONS:
        out.append(item)

    result: list[str] = []
    for item in out:
        if item and item not in result:
            result.append(item)
        if len(result) >= 3:
            break
    return result


async def workbench_suggestions(user_id: int, *, refresh: bool = False) -> dict:
    now_mono = time.monotonic()
    cached = _CACHE.get(user_id)
    if cached and not refresh and now_mono - cached[0] < _TTL_SECONDS:
        return cached[1]
    if not refresh:
        from core.cache import get_json

        redis_cached = await get_json(f"workbench:suggestions:{user_id}")
        if isinstance(redis_cached, dict):
            _CACHE[user_id] = (time.monotonic(), redis_cached)
            return redis_cached

    context = await _context(user_id)
    suggestions = _fallback(context)
    source = "fallback"

    if settings.llm_api_key:
        try:
            from core.bots.registry import get_active_bot

            bot = await get_active_bot(user_id)
            enriched = await _llm_json(
                _SYSTEM,
                json.dumps(context, ensure_ascii=False, default=str),
                bot=bot,
            )
            candidates = enriched.get("suggestions") if enriched else None
            if isinstance(candidates, list):
                clean = []
                for value in candidates:
                    text = _short(value, 24)
                    if text and text not in clean:
                        clean.append(text)
                if clean:
                    suggestions = (clean + suggestions)[:3]
                    source = "llm"
        except Exception as exc:
            log.warning(f"[workbench] suggestion llm error: {exc}")

    generated = datetime.now()
    payload = {
        "suggestions": suggestions[:3],
        "source": source,
        "generated_at": generated.isoformat(timespec="seconds"),
        "expires_at": (generated + timedelta(seconds=_TTL_SECONDS)).isoformat(
            timespec="seconds"
        ),
    }
    _CACHE[user_id] = (time.monotonic(), payload)
    from core.cache import set_json

    await set_json(
        f"workbench:suggestions:{user_id}",
        payload,
        int(_TTL_SECONDS),
    )
    return payload
