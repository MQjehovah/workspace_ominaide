"""Backend-side information digest: summarise unread items, no desktop required."""

from __future__ import annotations

from core.logging import get_logger
log = get_logger(__name__)
from ai.llm.usage import tracked_create

from datetime import datetime, timedelta


async def build_digest(user_id: int, hours: int = 24, limit: int = 30) -> dict:
    from sqlalchemy import select
    from core.database.session import async_session
    from plugins.sources.backend.models import ContentItem, ContentSource

    since = datetime.utcnow() - timedelta(hours=max(1, hours))
    async with async_session() as db:
        rows = (await db.execute(
            select(ContentItem, ContentSource.title)
            .join(ContentSource, ContentItem.source_id == ContentSource.id)
            .where(
                ContentSource.user_id == user_id,
                ContentItem.read == False,  # noqa: E712
                ContentItem.created_at >= since,
            )
            .order_by(ContentItem.published.desc(), ContentItem.id.desc())
            .limit(max(1, limit))
        )).all()

    items = []
    for item, source_title in rows:
        items.append({
            "id": item.id,
            "title": item.title,
            "source": source_title or "",
            "link": item.link,
            "summary": (item.summary or item.content or "")[:300],
        })
    return {
        "user_id": user_id,
        "hours": hours,
        "count": len(items),
        "items": items,
    }


async def _llm_summary(digest: dict) -> str | None:
    from core.config.settings import settings

    if not settings.llm_api_key or not digest["items"]:
        return None
    try:
        from openai import AsyncOpenAI

        lines = [
            f"- [{x['source']}] {x['title']}：{(x['summary'] or '')[:160]}"
            for x in digest["items"]
        ]
        client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        resp = await tracked_create(client, 
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": (
                    "你是用户的资讯助理。根据下面未读内容，用 3-6 句中文总结今天值得关注的资讯："
                    "先给一句总览，再挑 2-4 条最重要的说明为什么值得看。不要 Markdown、不要列表、不要编造。"
                )},
                {"role": "user", "content": "\n".join(lines)},
            ],
            temperature=0.3,
        )
        return (resp.choices[0].message.content or "").strip() or None
    except Exception as e:
        log.warning(f"[sources] digest llm error: {e}")
        return None


def _fallback_summary(digest: dict) -> str:
    items = digest["items"][:5]
    if not items:
        return ""
    titles = "；".join(x["title"] for x in items)
    return f"今天有 {digest['count']} 篇未读资讯。重点标题：{titles}。"


async def generate_sources_digest(
    user_id: int,
    hours: int = 24,
    notify: bool = True,
) -> dict | None:
    """Build a digest and optionally push it as a notification."""
    digest = await build_digest(user_id, hours=hours)
    if not digest["items"]:
        return None
    summary = await _llm_summary(digest) or _fallback_summary(digest)
    digest["summary"] = summary

    if notify and summary:
        from core.database.session import async_session
        from plugins.notifications.backend.router import notify_user
        from plugins.notifications.backend.service import create_notification

        async with async_session() as db:
            n = await create_notification(
                db,
                user_id,
                "📰 今日资讯摘要",
                summary[:800],
                "sources_digest",
                "/sources",
                actions=[{"key": "open", "label": "阅读资讯", "kind": "open", "link": "/sources"}],
                dedupe_key=f"sources_digest:{datetime.utcnow().date().isoformat()}",
            )
            await db.commit()
            await notify_user(user_id, {
                "type": "new_notification",
                "id": n.id,
                "title": "📰 今日资讯摘要",
                "body": summary[:800],
                "link": "/sources",
            })
    return digest
