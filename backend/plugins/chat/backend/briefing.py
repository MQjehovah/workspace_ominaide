"""Daily briefing: AI-generated summary of today's schedule, notifications, articles."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from core.auth.dependencies import get_current_user
from core.config.settings import settings
from datetime import datetime, date

router = APIRouter(prefix="/api", tags=["briefing"])

class BriefingResponse(BaseModel):
    briefing: str
    generated_at: str


async def generate_briefing(user_id: int) -> str:
    """Core briefing logic — can be called from API or MCP tool."""
    today = date.today()
    start = datetime(today.year, today.month, today.day, 0, 0, 0)
    end = datetime(today.year, today.month, today.day, 23, 59, 59)

    data = {"schedule": [], "notifications": [], "articles": [], "profile": None}

    try:
        from sqlalchemy import select
        from plugins.schedule.backend.models import Event
        from core.database.session import async_session
        async with async_session() as db:
            r = await db.execute(select(Event).where(Event.user_id == user_id, Event.start_time >= start, Event.start_time <= end).order_by(Event.start_time))
            for ev in r.scalars().all():
                data["schedule"].append(f"{ev.title} ({ev.start_time.strftime('%H:%M')})")
    except Exception: pass

    try:
        from plugins.notifications.backend.models import Notification as NotifM
        from core.database.session import async_session
        async with async_session() as db:
            r = await db.execute(select(NotifM).where(NotifM.user_id == user_id, NotifM.read == False).order_by(NotifM.created_at.desc()).limit(5))
            for n in r.scalars().all():
                data["notifications"].append(n.title)
    except Exception: pass

    try:
        from plugins.rss.backend.models import Entry
        from core.database.session import async_session
        async with async_session() as db:
            r = await db.execute(select(Entry).where(Entry.published >= start, Entry.published <= end, Entry.read == False).order_by(Entry.published.desc()).limit(5))
            for art in r.scalars().all():
                data["articles"].append(art.title)
    except Exception: pass

    try:
        from core.auth.domain.models import UserProfile
        from core.database.session import async_session
        async with async_session() as db:
            r = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
            p = r.scalar_one_or_none()
            if p and p.name:
                data["profile"] = p.name
    except Exception: pass

    prompt_parts = [f"日期: {today.isoformat()}"]
    if data.get("profile"):
        prompt_parts.append(f"用户: {data['profile']}")
    if data["schedule"]:
        prompt_parts.append("今日日程:\n" + "\n".join(f"- {s}" for s in data["schedule"]))
    else:
        prompt_parts.append("今日无日程安排")
    if data["notifications"]:
        prompt_parts.append(f"未读通知:\n" + "\n".join(f"- {n}" for n in data["notifications"]))
    if data["articles"]:
        prompt_parts.append(f"今日新文章:\n" + "\n".join(f"- {a}" for a in data["articles"]))

    system_prompt = "你是一个个人AI助理，用自然语言为用户生成每日简报。语气友好、简洁。根据提供的信息，生成一段2-5句话的简报。用中文。"

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        resp = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": "\n".join(prompt_parts)}],
            temperature=0.7, max_tokens=500,
        )
        return resp.choices[0].message.content or "暂无简报信息"
    except Exception as e:
        return f"生成简报失败: {str(e)}"


@router.get("/briefing", response_model=BriefingResponse)
async def get_briefing(user: dict = Depends(get_current_user)):
    briefing = await generate_briefing(user["id"])
    return BriefingResponse(briefing=briefing, generated_at=datetime.utcnow().isoformat())
