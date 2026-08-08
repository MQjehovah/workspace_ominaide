import json
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.config.settings import settings
from core.database.session import get_db, async_session
from core.auth.dependencies import get_current_user
from core.ai.agent import run_agent, run_agent_stream
from plugins.chat.backend.schemas import ChatRequest, ChatResponse, ChatHistoryItem, TranslateRequest, TranslateResponse
from plugins.chat.backend.memory import build_context

router = APIRouter(prefix="/api/chat", tags=["chat"])


async def save_message(user_id: int, role: str, content: str):
    from plugins.chat.backend.models import ChatMessage
    if not content:
        return
    try:
        async with async_session() as db:
            db.add(ChatMessage(user_id=user_id, role=role, content=content))
            await db.commit()
    except Exception:
        pass


@router.get("/history", response_model=list[ChatHistoryItem])
async def list_history(
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from plugins.chat.backend.models import ChatMessage
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == user["id"])
        .order_by(ChatMessage.id.desc())
        .limit(limit)
    )
    messages = list(reversed(result.scalars().all()))
    return [ChatHistoryItem.model_validate(m) for m in messages]


@router.delete("/history")
async def clear_history(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import delete
    from plugins.chat.backend.models import ChatMessage
    await db.execute(delete(ChatMessage).where(ChatMessage.user_id == user["id"]))
    await db.commit()
    return {"message": "Chat history cleared"}


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    """Direct LLM chat (no agent/tools). Use for plain Q&A, writing, editor AI features."""
    if not settings.llm_api_key:
        raise HTTPException(status_code=400, detail="LLM API key not configured")
    try:
        from openai import AsyncOpenAI
        messages: list[dict] = []
        if req.history:
            for m in req.history:
                messages.append({"role": m.role, "content": m.content})
        user_content: str | list = req.message
        if req.images:
            parts: list = [{"type": "text", "text": req.message}]
            for img in req.images[:6]:
                if isinstance(img, str) and img.startswith("data:"):
                    parts.append({"type": "image_url", "image_url": {"url": img}})
            if len(parts) > 1:
                user_content = parts
        messages.append({"role": "user", "content": user_content})
        client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        resp = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=0.7,
        )
        reply = (resp.choices[0].message.content or "").strip()
        await save_message(user["id"], "user", req.message)
        await save_message(user["id"], "assistant", reply)
        return ChatResponse(reply=reply)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agent", response_model=ChatResponse)
async def chat_agent(req: ChatRequest, user: dict = Depends(get_current_user)):
    """Agent chat: runs the AI agent with tool-calling and user context."""
    if not settings.llm_api_key:
        raise HTTPException(status_code=400, detail="LLM API key not configured")

    messages = []
    ctx = await build_context(user["id"], req.message)
    if ctx:
        messages.append({"role": "system", "content": ctx})
    if req.history:
        for m in req.history:
            messages.append({"role": m.role, "content": m.content})

    user_content: str | list = req.message
    if req.images:
        parts: list = [{"type": "text", "text": req.message}]
        for img in req.images[:6]:
            if isinstance(img, str) and img.startswith("data:"):
                parts.append({"type": "image_url", "image_url": {"url": img}})
        if len(parts) > 1:
            user_content = parts
    messages.append({"role": "user", "content": user_content})

    try:
        reply = await run_agent(user["id"], messages, max_turns=30)
        await save_message(user["id"], "user", req.message)
        await save_message(user["id"], "assistant", reply)
        return ChatResponse(reply=reply)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
async def chat_stream(req: ChatRequest, user: dict = Depends(get_current_user)):
    if not settings.llm_api_key:
        raise HTTPException(status_code=400, detail="LLM API key not configured")

    messages = []
    ctx = await build_context(user["id"], req.message)
    if ctx:
        messages.append({"role": "system", "content": ctx})
    if req.history:
        for m in req.history:
            messages.append({"role": m.role, "content": m.content})

    user_content: str | list = req.message
    if req.images:
        parts: list = [{"type": "text", "text": req.message}]
        for img in req.images[:6]:
            if isinstance(img, str) and img.startswith("data:"):
                parts.append({"type": "image_url", "image_url": {"url": img}})
        if len(parts) > 1:
            user_content = parts
    messages.append({"role": "user", "content": user_content})

    await save_message(user["id"], "user", req.message)

    async def event_stream():
        reply_parts = []
        try:
            async for event in run_agent_stream(user["id"], messages, max_turns=30):
                if event.startswith("data: "):
                    try:
                        payload = json.loads(event[6:].strip())
                        if payload.get("type") == "token":
                            reply_parts.append(payload.get("content", ""))
                    except Exception:
                        pass
                yield event
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        await save_message(user["id"], "assistant", "".join(reply_parts))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/translate", response_model=TranslateResponse)
async def translate(req: TranslateRequest, user: dict = Depends(get_current_user)):
    """Direct LLM translation (no agent/tools)."""
    if not settings.llm_api_key:
        raise HTTPException(status_code=400, detail="LLM API key not configured")
    lang_map = {"zh": "中文", "en": "English", "ja": "日语", "ko": "韩语", "fr": "法语", "de": "德语", "es": "西班牙语", "ru": "俄语"}
    target_lang = lang_map.get(req.target, req.target)
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        resp = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": f"你是一个专业翻译。请把用户文本翻译成{target_lang}。只返回翻译结果，不要任何解释或多余内容。保持原意、语气和格式。"},
                {"role": "user", "content": req.text},
            ],
            temperature=0.2,
        )
        translated = (resp.choices[0].message.content or "").strip()
        return TranslateResponse(text=req.text, translated=translated)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
