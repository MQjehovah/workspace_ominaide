import json
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.config.settings import settings
from core.database.session import get_db, async_session
from core.auth.dependencies import get_current_user
from core.ai.agent import run_agent, run_agent_stream
from plugins.chat.backend.schemas import ChatRequest, ChatResponse, ChatHistoryItem
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
    messages.append({"role": "user", "content": req.message})

    await save_message(user["id"], "user", req.message)

    async def event_stream():
        reply_parts = []
        try:
            async for event in run_agent_stream(user["id"], messages):
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
