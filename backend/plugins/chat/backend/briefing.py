"""Daily briefing: AI uses agent with MCP tools to gather info and generate a summary."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from core.auth.dependencies import get_current_user
from core.ai.agent import run_agent
from plugins.chat.backend.memory import build_context
from datetime import datetime

router = APIRouter(prefix="/api", tags=["briefing"])

class BriefingResponse(BaseModel):
    briefing: str
    generated_at: str


async def generate_briefing(user_id: int) -> str:
    """Agent-generated briefing using MCP tools (schedule, notifications, articles, profile)."""
    ctx = await build_context(user_id)
    messages = []
    if ctx:
        messages.append({"role": "system", "content": ctx})
    messages.append({"role": "system", "content": "你是一个主动的个人AI助理。用户请求每日简报。请调用工具获取相关信息，然后生成一段友好、简洁的简报，总结今日日程、未读通知和新文章。用中文。"})
    messages.append({"role": "user", "content": "帮我生成今天的每日简报"})

    return await run_agent(user_id, messages)


@router.get("/briefing", response_model=BriefingResponse)
async def get_briefing(user: dict = Depends(get_current_user)):
    briefing = await generate_briefing(user["id"])
    return BriefingResponse(briefing=briefing, generated_at=datetime.utcnow().isoformat())
