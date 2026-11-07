
from core.logging import get_logger
log = get_logger(__name__)
import asyncio
import base64
import json
import time
from datetime import datetime
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from core.config.settings import settings
from core.database.session import get_db, async_session
from core.auth.dependencies import get_current_user
from core.ai.agent import run_agent, run_agent_stream
from core.bots import runner
from core.bots.context import (
    reset_current_bot_id,
    reset_current_session_id,
    set_current_bot_id,
    set_current_session_id,
)
from core.bots.memory import build_bot_context
from core.bots.registry import BotNotFound, get_active_bot, get_or_create_default_bot
from plugins.chat.backend.schemas import (
    ChatRequest, ChatResponse, ChatHistoryItem, TranslateRequest, TranslateResponse,
    AsrResponse, TtsRequest, SessionItem, SessionRename,
)
from plugins.chat.backend.voice_stream import (
    edge_failed, edge_ready, edge_succeeded,
    iter_agent_events, trim_silence, tts_edge_pcm, tts_pcm,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])

DEFAULT_SESSION = "default"


async def _resolve_bot(user_id: int, bot_id: int | None):
    try:
        return await get_active_bot(user_id, bot_id)
    except BotNotFound:
        raise HTTPException(status_code=404, detail="Bot not found")


async def _upsert_session(db: AsyncSession, user_id: int, session_id: str, role: str, content: str, bot=None):
    from plugins.chat.backend.models import ChatSession
    r = await db.execute(
        select(ChatSession).where(ChatSession.user_id == user_id, ChatSession.session_id == session_id)
    )
    s = r.scalar_one_or_none()
    if s is None:
        s = ChatSession(
            user_id=user_id,
            session_id=session_id,
            bot_id=bot.id if bot is not None else None,
        )
        db.add(s)
    elif bot is not None and s.bot_id is None:
        s.bot_id = bot.id
    s.updated_at = datetime.utcnow()
    if not s.title and role == "user" and content:
        s.title = content[:30]


async def save_message(user_id: int, role: str, content: str, session_id: str = DEFAULT_SESSION, bot=None):
    from plugins.chat.backend.models import ChatMessage
    if not content:
        return
    try:
        async with async_session() as db:
            db.add(ChatMessage(
                user_id=user_id,
                session_id=session_id,
                role=role,
                content=content,
                bot_id=bot.id if bot is not None else None,
            ))
            await _upsert_session(db, user_id, session_id, role, content, bot)
            await db.commit()
    except Exception:
        pass


async def load_history(user_id: int, session_id: str, limit: int, bot=None) -> list[dict]:
    """Load the most recent messages of a session in chronological order."""
    from plugins.chat.backend.models import ChatMessage
    conds = [ChatMessage.user_id == user_id, ChatMessage.session_id == session_id]
    if bot is not None:
        if bot.is_default:
            # NULL = history written before the bot layer existed.
            conds.append(or_(ChatMessage.bot_id == bot.id, ChatMessage.bot_id.is_(None)))
        else:
            conds.append(ChatMessage.bot_id == bot.id)
    async with async_session() as db:
        result = await db.execute(
            select(ChatMessage)
            .where(*conds)
            .order_by(ChatMessage.id.desc())
            .limit(limit)
        )
        rows = list(reversed(result.scalars().all()))
        return [{"role": m.role, "content": m.content} for m in rows]


async def resolve_history(req: ChatRequest, user_id: int, limit: int | None = None, bot=None) -> list[dict]:
    """Client-provided history wins; otherwise auto-load from the session store."""
    if req.history is not None:
        return [{"role": m.role, "content": m.content} for m in req.history]
    return await load_history(
        user_id, req.session_id or DEFAULT_SESSION,
        limit or settings.chat_history_limit,
        bot=bot,
    )


def _user_content(req: ChatRequest):
    """Build the final user message, attaching inline images when present."""
    if not req.images:
        return req.message
    parts: list = [{"type": "text", "text": req.message}]
    for img in req.images[:6]:
        if isinstance(img, str) and img.startswith("data:"):
            parts.append({"type": "image_url", "image_url": {"url": img}})
    return parts if len(parts) > 1 else req.message


async def build_messages(
    req: ChatRequest,
    user_id: int,
    *,
    bot=None,
    persona: bool = True,
    extra_system: str | None = None,
    history_limit: int | None = None,
) -> list[dict]:
    messages: list[dict] = []
    persona_text = (
        bot.system_prompt
        if bot is not None and bot.system_prompt
        else settings.assistant_system_prompt
    )
    if persona and persona_text:
        messages.append({"role": "system", "content": persona_text})
    if extra_system:
        messages.append({"role": "system", "content": extra_system})
    ctx = await build_bot_context(user_id, bot, req.message)
    if ctx:
        messages.append({"role": "system", "content": ctx})
    from core.skills.runtime import build_skill_context

    skill_ctx = await build_skill_context(bot)
    if skill_ctx:
        messages.append({"role": "system", "content": skill_ctx})
    if req.context_refs:
        from core.objects.registry import build_context_block

        block = await build_context_block(
            user_id,
            [ref.model_dump() for ref in req.context_refs],
            req.context_comment_id,
        )
        if block:
            messages.append({"role": "system", "content": block})
    messages.extend(await resolve_history(req, user_id, limit=history_limit, bot=bot))
    messages.append({"role": "user", "content": _user_content(req)})
    return messages


@router.get("/history", response_model=list[ChatHistoryItem])
async def list_history(
    limit: int = Query(50, ge=1, le=200),
    session_id: str | None = Query(None),
    before_id: int | None = Query(None),
    bot_id: int | None = Query(None),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from plugins.chat.backend.models import ChatMessage
    q = select(ChatMessage).where(ChatMessage.user_id == user["id"])
    if session_id:
        q = q.where(ChatMessage.session_id == session_id)
    if before_id is not None:
        q = q.where(ChatMessage.id < before_id)
    if bot_id is not None:
        bot = await _resolve_bot(user["id"], bot_id)
        q = q.where(
            or_(ChatMessage.bot_id == bot.id, ChatMessage.bot_id.is_(None))
            if bot.is_default
            else ChatMessage.bot_id == bot.id
        )
    result = await db.execute(q.order_by(ChatMessage.id.desc()).limit(limit))
    messages = list(reversed(result.scalars().all()))
    return [ChatHistoryItem.model_validate(m) for m in messages]


@router.delete("/history")
async def clear_history(
    session_id: str | None = Query(None),
    bot_id: int | None = Query(None),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from plugins.chat.backend.models import ChatMessage, ChatSession
    cond = [ChatMessage.user_id == user["id"]]
    if session_id:
        cond.append(ChatMessage.session_id == session_id)
    sess_cond = [ChatSession.user_id == user["id"]]
    if session_id:
        sess_cond.append(ChatSession.session_id == session_id)
    if bot_id is not None:
        bot = await _resolve_bot(user["id"], bot_id)
        msg_bot = (
            or_(ChatMessage.bot_id == bot.id, ChatMessage.bot_id.is_(None))
            if bot.is_default
            else ChatMessage.bot_id == bot.id
        )
        cond.append(msg_bot)
        sess_cond.append(ChatSession.bot_id == bot.id)
    await db.execute(delete(ChatMessage).where(*cond))
    if session_id or bot_id is not None:
        await db.execute(delete(ChatSession).where(*sess_cond))
    await db.commit()
    return {"message": "Chat history cleared"}


@router.get("/sessions", response_model=list[SessionItem])
async def list_sessions(
    bot_id: int | None = Query(None),
    user: dict = Depends(get_current_user),
):
    from plugins.chat.backend.models import ChatSession
    async with async_session() as db:
        q = select(ChatSession).where(ChatSession.user_id == user["id"])
        if bot_id is not None:
            bot = await _resolve_bot(user["id"], bot_id)
            q = q.where(
                or_(ChatSession.bot_id == bot.id, ChatSession.bot_id.is_(None))
                if bot.is_default
                else ChatSession.bot_id == bot.id
            )
        r = await db.execute(q.order_by(ChatSession.updated_at.desc()).limit(100))
        return [
            SessionItem(
                session_id=s.session_id,
                title=s.title,
                updated_at=s.updated_at,
                bot_id=s.bot_id,
            )
            for s in r.scalars().all()
        ]


@router.patch("/sessions/{session_id}")
async def rename_session(
    session_id: str,
    req: SessionRename,
    user: dict = Depends(get_current_user),
):
    from plugins.chat.backend.models import ChatSession
    title = (req.title or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="title is required")
    async with async_session() as db:
        row = (await db.execute(
            select(ChatSession).where(
                ChatSession.user_id == user["id"],
                ChatSession.session_id == session_id,
            )
        )).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Session not found")
        row.title = title[:200]
        row.updated_at = datetime.utcnow()
        await db.commit()
    return {"message": "Renamed", "title": title[:200]}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    bot_id: int | None = Query(None),
    user: dict = Depends(get_current_user),
):
    from plugins.chat.backend.models import ChatMessage, ChatSession
    async with async_session() as db:
        msg_cond = [ChatMessage.user_id == user["id"], ChatMessage.session_id == session_id]
        sess_cond = [ChatSession.user_id == user["id"], ChatSession.session_id == session_id]
        if bot_id is not None:
            bot = await _resolve_bot(user["id"], bot_id)
            if bot.is_default:
                msg_cond.append(
                    or_(ChatMessage.bot_id == bot.id, ChatMessage.bot_id.is_(None))
                )
            else:
                msg_cond.append(ChatMessage.bot_id == bot.id)
            sess_cond.append(ChatSession.bot_id == bot.id)
        await db.execute(delete(ChatMessage).where(*msg_cond))
        await db.execute(delete(ChatSession).where(*sess_cond))
        await db.commit()
    return {"message": "Session deleted"}


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    """Direct LLM chat (no agent/tools). Use for plain Q&A, writing, editor AI features."""
    if not settings.llm_api_key:
        raise HTTPException(status_code=400, detail="LLM API key not configured")
    session_id = req.session_id or DEFAULT_SESSION
    bot = await _resolve_bot(user["id"], req.bot_id) if req.bot_id else None
    try:
        from openai import AsyncOpenAI
        messages = await build_messages(req, user["id"], bot=bot, persona=False)
        client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        resp = await client.chat.completions.create(
            model=(bot.model if bot is not None and bot.model else settings.llm_model),
            messages=messages,
            temperature=(bot.temperature if bot is not None and bot.temperature is not None else 0.7),
        )
        reply = (resp.choices[0].message.content or "").strip()
        await save_message(user["id"], "user", req.message, session_id, bot=bot)
        await save_message(user["id"], "assistant", reply, session_id, bot=bot)
        return ChatResponse(reply=reply)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agent", response_model=ChatResponse)
async def chat_agent(req: ChatRequest, user: dict = Depends(get_current_user)):
    """Agent chat: runs the personal-assistant agent with tool-calling and user context."""
    if not settings.llm_api_key:
        raise HTTPException(status_code=400, detail="LLM API key not configured")
    session_id = req.session_id or DEFAULT_SESSION
    bot = await _resolve_bot(user["id"], req.bot_id)
    try:
        messages = await build_messages(req, user["id"], bot=bot)
        token = set_current_bot_id(bot.id)
        session_token = set_current_session_id(session_id)
        try:
            reply = await run_agent(
                user["id"],
                messages,
                tools_filter=bot.allowed_tools,
                max_turns=bot.max_turns or 30,
                model=bot.model,
                temperature=bot.temperature if bot.temperature is not None else 0.7,
            )
        finally:
            reset_current_session_id(session_token)
            reset_current_bot_id(token)
        await save_message(user["id"], "user", req.message, session_id, bot=bot)
        await save_message(user["id"], "assistant", reply, session_id, bot=bot)
        return ChatResponse(reply=reply)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
async def chat_stream(req: ChatRequest, user: dict = Depends(get_current_user)):
    if not settings.llm_api_key:
        raise HTTPException(status_code=400, detail="LLM API key not configured")

    session_id = req.session_id or DEFAULT_SESSION
    bot = await _resolve_bot(user["id"], req.bot_id)
    messages = await build_messages(req, user["id"], bot=bot)
    await save_message(user["id"], "user", req.message, session_id, bot=bot)

    async def event_stream():
        reply_parts = []
        token = set_current_bot_id(bot.id)
        session_token = set_current_session_id(session_id)
        try:
            async for event in run_agent_stream(
                user["id"],
                messages,
                tools_filter=bot.allowed_tools,
                max_turns=bot.max_turns or 30,
                model=bot.model,
                temperature=bot.temperature if bot.temperature is not None else 0.7,
            ):
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
        finally:
            reset_current_session_id(session_token)
            reset_current_bot_id(token)
            await save_message(user["id"], "assistant", "".join(reply_parts), session_id, bot=bot)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/runs")
async def chat_run(req: ChatRequest, user: dict = Depends(get_current_user)):
    """Create a persistent run. The client streams ``/api/runs/{id}/stream``."""
    if not settings.llm_api_key:
        raise HTTPException(status_code=400, detail="LLM API key not configured")
    session_id = req.session_id or DEFAULT_SESSION
    bot = await _resolve_bot(user["id"], req.bot_id)
    messages = await build_messages(req, user["id"], bot=bot)
    await save_message(user["id"], "user", req.message, session_id, bot=bot)
    run = await runner.create_run(
        user["id"],
        bot,
        req.message,
        messages=messages,
        trigger="chat",
        session_id=session_id,
    )
    return {
        "run_id": run.id,
        "bot_id": bot.id,
        "status": run.status,
        "stream": f"/api/runs/{run.id}/stream",
    }


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
        speech_kwargs = {
            "model": req.model or settings.tts_model,
            "input": text,
            "voice": req.voice or settings.tts_voice,
        }
        if settings.tts_send_format:
            speech_kwargs["response_format"] = fmt
        speech = await client.audio.speech.create(**speech_kwargs)
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


def _weather_text(code: int) -> str:
    if code == 0:
        return "晴"
    if code <= 2:
        return "多云"
    if code == 3:
        return "阴"
    if code in (45, 48):
        return "雾"
    if code <= 57:
        return "毛毛雨"
    if code <= 67:
        return "雨"
    if code <= 77:
        return "雪"
    if code <= 82:
        return "阵雨"
    if code <= 86:
        return "阵雪"
    return "雷雨"


async def _voice_context() -> str:
    """Small always-on context so common questions skip slow tool calls."""
    from plugins.device.backend.router import _current_weather

    now = datetime.now()
    weekday = "一二三四五六日"[now.weekday()]
    text = f"当前时间：{now:%Y-%m-%d} 星期{weekday} {now:%H:%M}。"
    try:
        weather = await _current_weather()
    except Exception:
        weather = None
    if weather:
        text += f"当前天气：{weather['temp']}℃，{_weather_text(weather['code'])}。"
    text += "时间和天气已在上下文中，回答这类问题不要调用工具。"
    return text


@router.post("/voice")
async def voice(
    file: UploadFile = File(...),
    session_id: str = Form(DEFAULT_SESSION),
    voice: str | None = Form(None),
    bot_id: int | None = Form(None),
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

    bot = await _resolve_bot(user["id"], bot_id)
    req = ChatRequest(message=transcript, session_id=session_id or DEFAULT_SESSION, bot_id=bot.id)
    try:
        voice_system = VOICE_STYLE + await _voice_context()
        messages = await build_messages(req, user["id"], bot=bot, extra_system=voice_system, history_limit=6)
        token = set_current_bot_id(bot.id)
        session_token = set_current_session_id(session_id or DEFAULT_SESSION)
        try:
            reply = await run_agent(
                user["id"],
                messages,
                tools_filter=bot.allowed_tools,
                max_turns=bot.max_turns or 30,
                model=bot.model,
                temperature=bot.temperature if bot.temperature is not None else 0.7,
            )
        finally:
            reset_current_session_id(session_token)
            reset_current_bot_id(token)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Agent failed: {e}")

    await save_message(user["id"], "user", transcript, session_id or DEFAULT_SESSION, bot=bot)
    await save_message(user["id"], "assistant", reply, session_id or DEFAULT_SESSION, bot=bot)

    try:
        tts_client = AsyncOpenAI(api_key=tts_key, base_url=settings.tts_base_url)
        speech_kwargs = {
            "model": settings.tts_model,
            "input": reply or transcript,
            "voice": voice or settings.tts_voice,
        }
        if settings.tts_send_format:
            speech_kwargs["response_format"] = settings.tts_format
        speech = await tts_client.audio.speech.create(**speech_kwargs)
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


async def _synthesize_voice_reply(text: str, tts_client, voice: str | None,
                                  edge_voice: str | None):
    """Prefer fast edge-tts; fall back to the OpenAI-compatible gateway."""
    if settings.tts_provider == "edge" and edge_ready():
        try:
            pcm, rate = await asyncio.wait_for(tts_edge_pcm(text, edge_voice), timeout=6)
            if pcm:
                edge_succeeded()
                return pcm, rate, "edge"
        except Exception as e:
            log.warning("[voice_stream] edge tts failed: %s", e)
            edge_failed(120)
    for attempt in range(3):
        try:
            pcm, rate = await tts_pcm(text, tts_client, voice)
            if pcm:
                return pcm, rate, "gateway"
        except Exception as e:
            log.warning("[voice_stream] gateway tts error attempt=%s: %s", attempt + 1, e)
        if attempt < 2:
            await asyncio.sleep(0.4 * (attempt + 1))
    return b"", 24000, "none"


@router.post("/voice/stream")
async def voice_stream(
    file: UploadFile = File(...),
    session_id: str = Form(DEFAULT_SESSION),
    voice: str | None = Form(None),
    bot_id: int | None = Form(None),
    user: dict = Depends(get_current_user),
):
    """Low-latency voice: ASR once, then stream agent text + sentence-level TTS.

    NDJSON frames:
      {"t":"transcript","text":...}
      {"t":"status","text":...}
      {"t":"delta","text":...}
      {"t":"audio","rate":24000,"pcm":"<base64 mono s16le>"}
      {"t":"done","reply":...}
    """
    t_start = time.monotonic()
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

    sid = session_id or DEFAULT_SESSION
    bot = await _resolve_bot(user["id"], bot_id)
    req = ChatRequest(message=transcript, session_id=sid, bot_id=bot.id)
    voice_system = VOICE_STYLE + await _voice_context()
    messages = await build_messages(req, user["id"], bot=bot, extra_system=voice_system, history_limit=6)
    await save_message(user["id"], "user", transcript, sid, bot=bot)

    out_q: asyncio.Queue = asyncio.Queue(maxsize=64)

    async def supervisor():
        t_first_token = None
        reply_parts: list[str] = []
        tts_client = AsyncOpenAI(api_key=tts_key, base_url=settings.tts_base_url)
        edge_voice = voice if voice and voice != settings.tts_voice else None
        token = set_current_bot_id(bot.id)
        session_token = set_current_session_id(sid)
        try:
            async for ev in iter_agent_events(
                run_agent_stream(
                    user["id"],
                    messages,
                    tools_filter=bot.allowed_tools,
                    max_turns=bot.max_turns or 30,
                    model=bot.model,
                    temperature=bot.temperature if bot.temperature is not None else 0.7,
                )
            ):
                typ = ev.get("type")
                if typ == "token":
                    text = ev.get("content") or ""
                    if not text:
                        continue
                    if t_first_token is None:
                        t_first_token = time.monotonic()
                    reply_parts.append(text)
                    await out_q.put({"t": "delta", "text": text})
                elif typ in ("tool_call", "tool_result"):
                    await out_q.put({"t": "status", "text": "正在执行工具..."})
        except Exception as e:
            await out_q.put({"t": "status", "text": f"处理失败：{e}"[:120]})
        finally:
            reset_current_session_id(session_token)
            reset_current_bot_id(token)

        reply = "".join(reply_parts).strip() or "已执行。"
        t_tts = time.monotonic()
        pcm, rate, provider = await _synthesize_voice_reply(
            reply, tts_client, voice, edge_voice)
        t_audio = time.monotonic()
        if pcm:
            pcm = trim_silence(pcm, rate)
        if pcm:
            for i in range(0, len(pcm), 6000):
                await out_q.put({
                    "t": "audio",
                    "rate": rate,
                    "pcm": base64.b64encode(pcm[i:i + 6000]).decode(),
                })
        else:
            await out_q.put({"t": "status", "text": "语音合成失败"})

        elapsed = time.monotonic() - t_start
        log.info(
            "[voice_stream] provider=%s first_token=%.2fs tts=%.2fs "
            "first_audio=%.2fs total=%.2fs",
            provider,
            t_first_token - t_start if t_first_token else -1,
            t_audio - t_tts,
            t_audio - t_start,
            elapsed,
        )
        await save_message(user["id"], "assistant", reply, sid, bot=bot)
        await out_q.put({"t": "done", "reply": reply})

    async def gen():
        yield json.dumps({"t": "transcript", "text": transcript}, ensure_ascii=False) + "\n"
        task = asyncio.create_task(supervisor())
        try:
            while True:
                item = await out_q.get()
                yield json.dumps(item, ensure_ascii=False) + "\n"
                if item.get("t") == "done":
                    break
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    return StreamingResponse(
        gen(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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
