from fastapi import APIRouter, Depends, HTTPException
from core.config.settings import settings
from core.auth.dependencies import get_current_user
from core.ai.agent import run_agent
from plugins.chat.backend.schemas import ChatRequest, ChatResponse
from plugins.chat.backend.memory import build_context

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    if not settings.llm_api_key:
        raise HTTPException(status_code=400, detail="LLM API key not configured")

    messages = []
    ctx = await build_context(user["id"], req.message)
    if ctx:
        messages.append({"role": "system", "content": ctx})
    if req.history:
        for m in req.history:
            messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": req.message})

    try:
        reply = await run_agent(user["id"], messages)
        return ChatResponse(reply=reply)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
