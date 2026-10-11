import json
from datetime import datetime
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from core.config.settings import settings
from core.database.session import get_db, async_session
from core.auth.dependencies import get_current_user
from core.ai.agent import run_agent, run_agent_stream
from plugins.chat.backend.schemas import (
    ChatRequest, ChatResponse, ChatHistoryItem, TranslateRequest, TranslateResponse,
    AsrResponse, TtsRequest, SessionItem,
)
from plugins.chat.backend.memory import build_context

router = APIRouter(prefix="/api/chat", tags=["chat"])

DEFAULT_SESSION = "default"


async def _upsert_session(db: AsyncSession, user_id: int, session_id: str, role: str, content: str):
    from plugins.chat.backend.models import ChatSession
    r = await db.execute(
        select(ChatSession).where(ChatSession.user_id == user_id, ChatSession.session_id == session_id)
    )
    s = r.scalar_one_or_none()
    if s is None:
        s = ChatSession(user_id=user_id, session_id=session_id)
        db.add(s)
    s.updated_at = datetime.utcnow()
    if not s.title and role == "user" and content:
        s.title = content[:30]


async def save_message(user_id: int, role: str, content: str, session_id: str = DEFAULT_SESSION):
    from plugins.chat.backend.models import ChatMessage
    if not content:
        return
    try:
        async with async_session() as db:
            db.add(ChatMessage(user_id=user_id, session_id=session_id, role=role, content=content))
            await _upsert_session(db, user_id, session_id, role, content)
            await db.commit()
    except Exception:
        pass


async def load_history(user_id: int, session_id: str, limit: int) -> list[dict]:
    """Load the most recent messages of a session in chronological order."""
    from plugins.chat.backend.models import ChatMessage
    async with async_session() as db:
        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id, ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id.desc())
            .limit(limit)
        )
        rows = list(reversed(result.scalars().all()))
        return [{"role": m.role, "content": m.content} for m in rows]


async def resolve_history(req: ChatRequest, user_id: int) -> list[dict]:
    """Client-provided history wins; otherwise auto-load from the session store."""
    if req.history is not None:
        return [{"role": m.role, "content": m.content} for m in req.history]
    return await load_history(user_id, req.session_id or DEFAULT_SESSION, settings.chat_history_limit)


def _user_content(req: ChatRequest):
    """Build the final user message, attaching inline images when present."""
    if not req.images:
        return req.message
    parts: list = [{"type": "text", "text": req.message}]
    for img in req.images[:6]:
        if isinstance(img, str) and img.startswith("data:"):
            parts.append({"type": "image_url", "image_url": {"url": img}})
    return parts if len(parts) > 1 else req.message


async def build_messages(req: ChatRequest, user_id: int, *, persona: bool = True, extra_system: str | None = None) -> list[dict]:
    messages: list[dict] = []
    if persona and settings.assistant_system_prompt:
        messages.append({"role": "system", "content": settings.assistant_system_prompt})
    if extra_system:
        messages.append({"role": "system", "content": extra_system})
    ctx = await build_context(user_id, req.message)
    if ctx:
        messages.append({"role": "system", "content": ctx})
    messages.extend(await resolve_history(req, user_id))
    messages.append({"role": "user", "content": _user_content(req)})
    return messages


@router.get("/history", response_model=list[ChatHistoryItem])
async def list_history(
    limit: int = Query(50, ge=1, le=200),
    session_id: str | None = Query(None),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from plugins.chat.backend.models import ChatMessage
    q = select(ChatMessage).where(ChatMessage.user_id == user["id"])
    if session_id:
        q = q.where(ChatMessage.session_id == session_id)
    result = await db.execute(q.order_by(ChatMessage.id.desc()).limit(limit))
    messages = list(reversed(result.scalars().all()))
    return [ChatHistoryItem.model_validate(m) for m in messages]


@router.delete("/history")
async def clear_history(
    session_id: str | None = Query(None),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from plugins.chat.backend.models import ChatMessage, ChatSession
    cond = [ChatMessage.user_id == user["id"]]
    if session_id:
        cond.append(ChatMessage.session_id == session_id)
        await db.execute(delete(ChatSession).where(ChatSession.user_id == user["id"], ChatSession.session_id == session_id))
    await db.execute(delete(ChatMessage).where(*cond))
    await db.commit()
    return {"message": "Chat history cleared"}


@router.get("/sessions", response_model=list[SessionItem])
async def list_sessions(user: dict = Depends(get_current_user)):
    from plugins.chat.backend.models import ChatSession
    async with async_session() as db:
        r = await db.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user["id"])
            .order_by(ChatSession.updated_at.desc())
            .limit(100)
        )
        return [
            SessionItem(session_id=s.session_id, title=s.title, updated_at=s.updated_at)
            for s in r.scalars().all()
        ]


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    from plugins.chat.backend.models import ChatMessage, ChatSession
    async with async_session() as db:
        await db.execute(delete(ChatMessage).where(ChatMessage.user_id == user["id"], ChatMessage.session_id == session_id))
        await db.execute(delete(ChatSession).where(ChatSession.user_id == user["id"], ChatSession.session_id == session_id))
        await db.commit()
    return {"message": "Session deleted"}


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    """Direct LLM chat (no agent/tools). Use for plain Q&A, writing, editor AI features."""
    if not settings.llm_api_key:
        raise HTTPException(status_code=400, detail="LLM API key not configured")
    session_id = req.session_id or DEFAULT_SESSION
    try:
        from openai import AsyncOpenAI
        messages = await build_messages(req, user["id"], persona=False)
        client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        resp = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=0.7,
        )
        reply = (resp.choices[0].message.content or "").strip()
        await save_message(user["id"], "user", req.message, session_id)
        await save_message(user["id"], "assistant", reply, session_id)
        return ChatResponse(reply=reply)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agent", response_model=ChatResponse)
async def chat_agent(req: ChatRequest, user: dict = Depends(get_current_user)):
    """Agent chat: runs the personal-assistant agent with tool-calling and user context."""
    if not settings.llm_api_key:
        raise HTTPException(status_code=400, detail="LLM API key not configured")
    session_id = req.session_id or DEFAULT_SESSION
    try:
        messages = await build_messages(req, user["id"])
        reply = await run_agent(user["id"], messages, max_turns=30)
        await save_message(user["id"], "user", req.message, session_id)
        await save_message(user["id"], "assistant", reply, session_id)
        return ChatResponse(reply=reply)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
async def chat_stream(req: ChatRequest, user: dict = Depends(get_current_user)):
    if not settings.llm_api_key:
        raise HTTPException(status_code=400, detail="LLM API key not configured")

    session_id = req.session_id or DEFAULT_SESSION
    messages = await build_messages(req, user["id"])
    await save_message(user["id"], "user", req.message, session_id)

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
        await save_message(user["id"], "assistant", "".join(reply_parts), session_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/asr", response_model=AsrResponse)
async def asr(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Speech-to-text. Wraps the upstream ASR (Zhipu glm-asr by default)."""
    api_key = settings.asr_api_key or settings.llm_api_key
    if not api_key:
        raise HTTPException(status_code=400, detail="ASR API key not configured")
    try:
        from openai import AsyncOpenAI
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Empty audio file")
        client = AsyncOpenAI(api_key=api_key, base_url=settings.asr_base_url)
        tr = await client.audio.transcriptions.create(
            model=settings.asr_model,
            file=(file.filename or "audio.wav", data, file.content_type or "audio/wav"),
        )
        return AsrResponse(text=(getattr(tr, "text", "") or "").strip())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ASR failed: {e}")


@router.post("/tts")
async def tts(req: TtsRequest, user: dict = Depends(get_current_user)):
    """Text-to-speech. Wraps the upstream TTS (Zhipu glm-tts by default), returns audio bytes."""
    api_key = settings.tts_api_key or settings.llm_api_key
    if not api_key:
        raise HTTPException(status_code=400, detail="TTS API key not configured")
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")
    fmt = req.format or settings.tts_format
    media = "audio/wav" if fmt.lower() == "wav" else "audio/mpeg"
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key, base_url=settings.tts_base_url)
        speech = await client.audio.speech.create(
            model=req.model or settings.tts_model,
            input=text,
            voice=req.voice or settings.tts_voice,
            response_format=fmt,
        )
        audio = getattr(speech, "content", None)
        if audio is None:
            audio = await speech.aread() if hasattr(speech, "aread") else speech.read()
        return Response(content=audio, media_type=media)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TTS failed: {e}")


VOICE_STYLE = (
    "当前是语音对话：请用口语化、简短直接的方式回答，控制在 50 字以内，"
    "不要使用 Markdown、列表或表情符号。"
)


@router.post("/voice")
async def voice(
    file: UploadFile = File(...),
    session_id: str = Form(DEFAULT_SESSION),
    voice: str | None = Form(None),
    user: dict = Depends(get_current_user),
):
    """Audio in → agent (tools/memory) → audio out.

    Response body is the synthesized WAV; the recognized text and the reply are
    returned in URL-encoded `X-Transcript` / `X-Reply` headers.
    """
    asr_key = settings.asr_api_key or settings.llm_api_key
    tts_key = settings.tts_api_key or settings.llm_api_key
    if not asr_key:
        raise HTTPException(status_code=400, detail="ASR API key not configured")
    if not tts_key:
        raise HTTPException(status_code=400, detail="TTS API key not configured")
    if not settings.llm_api_key:
        raise HTTPException(status_code=400, detail="LLM API key not configured")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio file")

    from openai import AsyncOpenAI
    try:
        asr_client = AsyncOpenAI(api_key=asr_key, base_url=settings.asr_base_url)
        tr = await asr_client.audio.transcriptions.create(
            model=settings.asr_model,
            file=(file.filename or "audio.wav", data, file.content_type or "audio/wav"),
        )
        transcript = (getattr(tr, "text", "") or "").strip()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ASR failed: {e}")
    if not transcript:
        raise HTTPException(status_code=422, detail="No speech recognized")

    req = ChatRequest(message=transcript, session_id=session_id or DEFAULT_SESSION)
    try:
        messages = await build_messages(req, user["id"], extra_system=VOICE_STYLE)
        reply = await run_agent(user["id"], messages, max_turns=30)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Agent failed: {e}")

    await save_message(user["id"], "user", transcript, session_id or DEFAULT_SESSION)
    await save_message(user["id"], "assistant", reply, session_id or DEFAULT_SESSION)

    try:
        tts_client = AsyncOpenAI(api_key=tts_key, base_url=settings.tts_base_url)
        speech = await tts_client.audio.speech.create(
            model=settings.tts_model,
            input=reply or transcript,
            voice=voice or settings.tts_voice,
            response_format=settings.tts_format,
        )
        audio = getattr(speech, "content", None)
        if audio is None:
            audio = await speech.aread() if hasattr(speech, "aread") else speech.read()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TTS failed: {e}")

    media = "audio/wav" if settings.tts_format.lower() == "wav" else "audio/mpeg"
    return Response(
        content=audio,
        media_type=media,
        headers={
            "X-Transcript": quote(transcript, safe=""),
            "X-Reply": quote(reply or "", safe=""),
            "Access-Control-Expose-Headers": "X-Transcript, X-Reply",
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
