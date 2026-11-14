
from core.logging import get_logger
log = get_logger(__name__)
from ai.llm.usage import tracked_create
import asyncio
import base64
import json
import time
from datetime import datetime
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Response
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from core.config.settings import settings
from core.database.session import get_db, async_session
from core.auth.dependencies import get_current_user
from ai.agent.loop import run_agent, run_agent_stream
from ai.llm.clients import get_openai_client
from ai.bots import runner
from ai.bots.context import (
    reset_current_bot_id,
    reset_current_client_kind,
    reset_current_session_id,
    set_current_bot_id,
    set_current_client_kind,
    set_current_session_id,
)
from ai.bots.memory import build_bot_context
from ai.bots.registry import BotNotFound, get_active_bot, get_or_create_default_bot
from plugins.chat.backend.schemas import (
    ChatRequest, ChatResponse, ChatHistoryItem, TranslateRequest, TranslateResponse,
    AsrResponse, TtsRequest, SessionItem, SessionRename,
)
from plugins.chat.backend.voice_stream import (
    SentenceChunker, iter_agent_events, trim_silence, tts_gateway_stream, tts_pcm,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])

DEFAULT_SESSION = "default"
SSE_HEARTBEAT_SECONDS = 15


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
            status="active",
        )
        db.add(s)
    elif bot is not None and s.bot_id is None:
        s.bot_id = bot.id
    s.updated_at = datetime.utcnow()
    s.last_message_at = datetime.utcnow()
    if not s.title and role == "user" and content:
        s.title = content[:30]


async def save_message(
    user_id: int,
    role: str,
    content: str,
    session_id: str = DEFAULT_SESSION,
    bot=None,
    *,
    run_id: int | None = None,
    kind: str = "text",
    metadata: dict | None = None,
):
    from plugins.chat.backend.models import ChatMessage
    if not content:
        return
    try:
        async with async_session() as db:
            db.add(ChatMessage(
                user_id=user_id,
                session_id=session_id,
                role=role,
                kind=kind,
                content=content,
                bot_id=bot.id if bot is not None else None,
                run_id=run_id,
                meta=metadata or {},
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
    timing: dict | None = None,
    fast: bool = False,
) -> list[dict]:
    from ai.context_builder import ContextBuilder

    builder = ContextBuilder()
    persona_text = (
        bot.system_prompt
        if bot is not None and bot.system_prompt
        else settings.assistant_system_prompt
    )
    if persona and persona_text:
        builder.section("persona", persona_text, priority=100, required=True)
    from ai.mcp.gateway import gateway_instruction

    instruction = gateway_instruction()
    if instruction:
        builder.section("tool_gateway", instruction, priority=80, max_chars=4000)
    from ai.cognition.situation import situation_prompt

    t_situation = time.monotonic()
    situation = await situation_prompt(user_id)
    if timing is not None:
        timing["situation"] = time.monotonic() - t_situation
    if situation:
        builder.section(
            "situation",
            "当前用户情境：\n" + situation,
            priority=65,
            max_chars=4000,
        )
    if req.machine_id:
        from core.wschannel.hub import host_channel

        online = host_channel.machine_ids(user_id)
        if req.machine_id in online:
            machine_name = host_channel.machine_name(req.machine_id)
            builder.section(
                "machine",
                (
                    f"当前用户正在本地机器「{machine_name}」({req.machine_id}) 上对话。"
                    "除非用户明确要求其他机器，local_* 工具默认使用这台机器；"
                    "不要凭之前的上下文切换到其他在线机器。"
                ),
                priority=70,
                max_chars=2000,
            )
    client_kind = (req.client_kind or ("web" if not req.machine_id else "desktop")).lower()
    if client_kind == "web" and not req.machine_id:
        builder.section(
            "client_surface",
            (
                "当前请求来自 Web 云端会话。你运行在服务端，不直接运行在用户桌面上。"
                "历史对话里出现的本地机器状态可能已经过期，不要默认用户还在同一台电脑前。"
                "但你仍然可以调用 local_* 工具，在用户在线设备上执行设备端指令；"
                "多台设备在线时先用 list_local_machines 确认 machine_id。"
                "服务端项目源码用 project_file 或 delegate_agent 读取，不要用 local_file 访问服务端路径。"
            ),
            priority=75,
            required=True,
        )
    if extra_system:
        builder.section("extra", extra_system, priority=60, max_chars=4000)
    t_ctx = time.monotonic()
    if fast:
        # Voice turns must feel immediate. Memory retrieval needs an embedding
        # round-trip that can take a second; skip it rather than stall the
        # answer, the agent can still call memory tools.
        try:
            ctx = await asyncio.wait_for(
                build_bot_context(user_id, bot, req.message, timing=timing), timeout=0.6
            )
        except asyncio.TimeoutError:
            ctx = None
    else:
        ctx = await build_bot_context(user_id, bot, req.message, timing=timing)
    if timing is not None:
        timing["bot_context"] = time.monotonic() - t_ctx
    if ctx:
        builder.section("memory", ctx, priority=55, max_chars=12000)
        if "【相关来源】" in ctx:
            builder.section(
                "citation_hint",
                "使用【相关实体】【实体关系】【相关来源】中的信息回答时，"
                "保留来源的 [type:id] 引用标记，例如 [note:12] 或 [project:5]。",
                priority=54,
                max_chars=800,
            )
    from ai.skills.runtime import build_skill_context

    t_skill = time.monotonic()
    skill_ctx = await build_skill_context(bot)
    if timing is not None:
        timing["skill_context"] = time.monotonic() - t_skill
    if skill_ctx:
        builder.section("skills", skill_ctx, priority=50, max_chars=4000)
    if req.context_refs:
        from app.objects.registry import build_context_block

        block = await build_context_block(
            user_id,
            [ref.model_dump() for ref in req.context_refs],
            req.context_comment_id,
        )
        if block:
            builder.section("context_refs", block, priority=45, max_chars=12000)
    t_hist = time.monotonic()
    history = await resolve_history(req, user_id, limit=history_limit, bot=bot)
    if timing is not None:
        timing["history"] = time.monotonic() - t_hist
    builder.history(history)
    builder.user(_user_content(req))
    return await builder.build()


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
        q = select(ChatSession).where(
            ChatSession.user_id == user["id"],
            ChatSession.deleted_at.is_(None),
        )
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
                status=s.status,
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
    from core.sessions import service as session_service

    if not await session_service.delete_session(user["id"], session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session archived"}


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    """Direct LLM chat (no agent/tools). Use for plain Q&A, writing, editor AI features."""
    if not settings.llm_api_key:
        raise HTTPException(status_code=400, detail="LLM API key not configured")
    session_id = req.session_id or DEFAULT_SESSION
    bot = await _resolve_bot(user["id"], req.bot_id) if req.bot_id else None
    try:
        messages = await build_messages(req, user["id"], bot=bot, persona=False)
        client = get_openai_client(settings.llm_base_url, settings.llm_api_key)
        resp = await tracked_create(client, 
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
        client_kind = (req.client_kind or ("web" if not req.machine_id else "desktop")).lower()
        client_token = set_current_client_kind(client_kind)
        try:
            reply = await run_agent(
                user["id"],
                messages,
                tools_filter=bot.allowed_tools,
                max_turns=bot.max_turns or 60,
                model=bot.model,
                temperature=bot.temperature if bot.temperature is not None else 0.7,
                bot=bot,
                    session_id=session_id,
            )
        finally:
            reset_current_client_kind(client_token)
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
    await save_message(user["id"], "user", req.message, session_id, bot=bot)

    async def event_stream():
        reply_parts: list[str] = []
        token = set_current_bot_id(bot.id)
        session_token = set_current_session_id(session_id)
        queue: asyncio.Queue = asyncio.Queue()
        done_marker = object()

        async def produce():
            client_kind = (req.client_kind or ("web" if not req.machine_id else "desktop")).lower()
            client_token = set_current_client_kind(client_kind)
            try:
                # Build context inside the stream so the client gets headers
                # and heartbeats immediately, even when embeddings/DB are slow.
                messages = await build_messages(req, user["id"], bot=bot)
                async for event in run_agent_stream(
                    user["id"],
                    messages,
                    tools_filter=bot.allowed_tools,
                    max_turns=bot.max_turns or 60,
                    model=bot.model,
                    temperature=bot.temperature if bot.temperature is not None else 0.7,
                    bot=bot,
                    session_id=session_id,
                ):
                    await queue.put(event)
            except Exception as e:
                await queue.put(
                    f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
                )
            finally:
                reset_current_client_kind(client_token)
                await queue.put(done_marker)

        producer = asyncio.create_task(produce())
        sent_done = False
        pending_approval = False
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=SSE_HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    # Keep the SSE connection alive during long tool calls or
                    # desktop approvals; mobile clients time out after 90s idle.
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
                    continue
                if event is done_marker:
                    break
                if event.startswith("data: "):
                    try:
                        payload = json.loads(event[6:].strip())
                        if payload.get("type") == "token":
                            reply_parts.append(payload.get("content", ""))
                        elif payload.get("type") == "approval_required":
                            pending_approval = True
                        elif payload.get("type") == "done":
                            sent_done = True
                            if payload.get("pending_approval"):
                                pending_approval = True
                    except Exception:
                        pass
                yield event
            if not sent_done:
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
        finally:
            if not producer.done():
                producer.cancel()
                try:
                    await producer
                except asyncio.CancelledError:
                    pass
            reset_current_session_id(session_token)
            reset_current_bot_id(token)
            # Approval runs persist their own final answer after the decision.
            if not pending_approval:
                await save_message(
                    user["id"], "assistant", "".join(reply_parts), session_id, bot=bot
                )

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
    client_kind = (req.client_kind or ("web" if not req.machine_id else "desktop")).lower()
    client_token = set_current_client_kind(client_kind)
    try:
        run = await runner.create_run(
            user["id"],
            bot,
            req.message,
            messages=messages,
            trigger="chat",
            agent="chat",
            session_id=session_id,
            meta={"client_kind": client_kind, "machine_id": req.machine_id},
        )
    finally:
        reset_current_client_kind(client_token)
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
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Empty audio file")
        client = get_openai_client(settings.asr_base_url, api_key)
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
        client = get_openai_client(settings.tts_base_url, api_key)
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
    """Small always-on context so common questions skip slow tool calls.

    Weather is read from the device brief's cache only.  Calling the weather
    API here used to add up to 6 seconds to every voice request whenever the
    upstream weather endpoint was failing.
    """
    from plugins.device.backend.router import _weather_cache

    now = datetime.now()
    weekday = "一二三四五六日"[now.weekday()]
    text = f"当前时间：{now:%Y-%m-%d} 星期{weekday} {now:%H:%M}。"
    data = _weather_cache.get("data")
    ts = _weather_cache.get("t") or 0
    if data and time.time() - ts < 3600:
        text += f"当前天气：{data['temp']}℃，{_weather_text(data['code'])}。"
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

    try:
        asr_client = get_openai_client(settings.asr_base_url, asr_key)
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
        messages = await build_messages(req, user["id"], bot=bot, extra_system=voice_system, history_limit=6, fast=True)
        token = set_current_bot_id(bot.id)
        session_token = set_current_session_id(session_id or DEFAULT_SESSION)
        try:
            reply = await run_agent(
                user["id"],
                messages,
                tools_filter=bot.allowed_tools,
                max_turns=bot.max_turns or 60,
                model=bot.model,
                temperature=bot.temperature if bot.temperature is not None else 0.7,
                bot=bot,
                    session_id=session_id,
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
        tts_client = get_openai_client(settings.tts_base_url, tts_key)
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


async def _synthesize_voice_reply(text: str, tts_client, voice: str | None):
    """Synthesize the full reply with the OpenAI-compatible TTS gateway."""
    for attempt in range(3):
        try:
            pcm, rate = await tts_pcm(text, tts_client, voice)
            if pcm:
                return pcm, rate
        except Exception as e:
            log.warning("[voice_stream] tts error attempt=%s: %s", attempt + 1, e)
        if attempt < 2:
            await asyncio.sleep(0.4 * (attempt + 1))
    return b"", 24000


_voice_tasks: dict[str, asyncio.Task] = {}


class VoiceInterruptRequest(BaseModel):
    session_id: str = DEFAULT_SESSION


class VoiceToolRequest(BaseModel):
    name: str
    arguments: dict | str | None = None


@router.post("/voice/tool")
async def voice_tool(req: VoiceToolRequest, user: dict = Depends(get_current_user)):
    """Execute a MOSS-Live client tool through the OmniAide agent.

    MOSS only forwards text frames; the app calls this endpoint with the
    function name/arguments, and the regular agent (with all MCP tools) does
    the actual work. Read-only queries and side-effecting actions share the
    same executor, with different guardrails in the system prompt.
    """
    if req.name not in ("omniaide_query", "omniaide_action"):
        raise HTTPException(status_code=400, detail="未知工具")

    args = req.arguments
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            args = {"request": args}
    if not isinstance(args, dict):
        args = {}
    request_text = str(args.get("request") or "").strip()
    if not request_text:
        raise HTTPException(status_code=400, detail="缺少 request")

    bot = await _resolve_bot(user["id"], None)
    if req.name == "omniaide_query":
        rule = "这是一个只读查询，绝对不能修改任何数据。"
    else:
        rule = "这是一个操作请求，执行后报告结果；不要编造成功。"
    system = (
        "你是 OmniAide 的语音工具执行器。"
        f"{rule}"
        "直接使用可用工具完成请求，用一两句简短中文返回结果；"
        "信息不足时说明缺少什么，不要反问。"
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": request_text},
    ]
    token = set_current_bot_id(bot.id)
    session_token = set_current_session_id(f"voice-tool-{user['id']}")
    try:
        reply = await asyncio.wait_for(
            run_agent(
                user["id"],
                messages,
                tools_filter=bot.allowed_tools,
                max_turns=8,
                model=bot.model,
                temperature=0.3,
                bot=bot,
                session_id=f"voice-tool-{user['id']}",
            ),
            timeout=50,
        )
    except asyncio.TimeoutError:
        reply = "执行超时，任务可能仍在后台运行。"
    except Exception as e:
        reply = f"执行失败：{e}"
    finally:
        reset_current_session_id(session_token)
        reset_current_bot_id(token)

    output = (reply or "").strip()
    return {"output": output[:1500] or "没有返回结果"}


@router.get("/voice/moss")
async def moss_voice_config(user: dict = Depends(get_current_user)):
    """Gateway config for the MOSS-Live full-duplex WebSocket.

    The key is only handed to an authenticated app over HTTPS; the gateway
    itself performs upstream auth and transparent bidirectional proxying.
    """
    key = settings.moss_api_key or settings.asr_api_key or settings.llm_api_key
    if not key:
        raise HTTPException(status_code=400, detail="MOSS gateway key not configured")

    # MOSS-Live only keeps memory for the lifetime of one WebSocket session
    # (the gateway's ?user does not persist it in practice), so inject the
    # OmniAide long-term memory and the last voice turns into the instructions.
    bot = await _resolve_bot(user["id"], None)
    memory = ""
    try:
        memory = await asyncio.wait_for(
            build_bot_context(user["id"], bot, query=""), timeout=3
        ) or ""
    except Exception:
        memory = ""

    history = ""
    try:
        from plugins.chat.backend.models import ChatMessage

        async with async_session() as db:
            rows = (
                await db.execute(
                    select(ChatMessage)
                    .where(
                        ChatMessage.user_id == user["id"],
                        ChatMessage.session_id == "voice-mobile",
                    )
                    .order_by(ChatMessage.id.desc())
                    .limit(8)
                )
            ).scalars().all()
        for row in reversed(rows):
            role = "用户" if row.role == "user" else "助手"
            text = (row.content or "").strip().replace("\n", " ")
            if text:
                history += f"{role}: {text[:300]}\n"
    except Exception:
        history = ""

    instructions = (
        "用简体中文口语化回答，尽量简短，不要使用 Markdown。"
        "涉及用户个人数据或需要操作时，优先调用 omniaide_query / omniaide_action，不要凭空猜测。"
    )
    if memory:
        instructions += (
            "\n\n以下是用户的跨会话记忆，回答时自然使用，不要机械复述：\n"
            + memory[:3000]
        )
    if history:
        instructions += "\n\n最近几轮语音对话（可作为上下文）：\n" + history[:2000]

    return {
        "url": settings.moss_url,
        "model": settings.moss_model,
        "token": key,
        "user": str(user["id"]),
        "voice": settings.moss_voice,
        "persona": {
            "name": (bot.name or "OmniAide")[:64],
            "prompt": (
                bot.system_prompt
                or "你是 OmniAide 的语音助手，语气自然、简洁，像是在打电话。"
            )[:4000],
        },
        "instructions": instructions[:7000],
    }


class VoiceTurnLog(BaseModel):
    user_text: str = ""
    assistant_text: str = ""


@router.post("/voice/log")
async def voice_log(req: VoiceTurnLog, user: dict = Depends(get_current_user)):
    """Persist a completed voice turn so the next call can recall it."""
    bot = await _resolve_bot(user["id"], None)
    session_id = "voice-mobile"
    if req.user_text.strip():
        await save_message(
            user["id"], "user", req.user_text.strip()[:2000], session_id, bot=bot
        )
    if req.assistant_text.strip():
        await save_message(
            user["id"],
            "assistant",
            req.assistant_text.strip()[:4000],
            session_id,
            bot=bot,
        )
    return {"ok": True}


@router.post("/voice/interrupt")
async def voice_interrupt(req: VoiceInterruptRequest, user: dict = Depends(get_current_user)):
    """Stop the active voice turn for a session (barge-in)."""
    key = f"{user['id']}:{req.session_id or DEFAULT_SESSION}"
    task = _voice_tasks.get(key)
    if task and not task.done():
        task.cancel()
    return {"ok": True}


@router.post("/voice/stream")
async def voice_stream(
    file: UploadFile | None = File(None),
    transcript: str | None = Form(None),
    session_id: str = Form(DEFAULT_SESSION),
    voice: str | None = Form(None),
    bot_id: int | None = Form(None),
    user: dict = Depends(get_current_user),
):
    """Low-latency voice turn: ASR (optional), streamed text, sentence-level TTS.

    Pass ``transcript`` to skip ASR when the client already has a final
    on-device recognition result.

    NDJSON frames:
      {"t":"transcript","text":...}
      {"t":"status","text":...}
      {"t":"delta","text":...}
      {"t":"audio","seq":0,"text":"...","rate":24000,"pcm":"<base64 s16le>"}
      {"t":"done","reply":...,"interrupted":false}
    """
    t_start = time.monotonic()
    tts_key = settings.tts_api_key or settings.llm_api_key
    if not settings.llm_api_key:
        raise HTTPException(status_code=400, detail="LLM API key not configured")
    if not tts_key:
        raise HTTPException(status_code=400, detail="TTS API key not configured")

    sid = session_id or DEFAULT_SESSION
    text = (transcript or "").strip()
    if not text:
        asr_key = settings.asr_api_key or settings.llm_api_key
        if not asr_key:
            raise HTTPException(status_code=400, detail="ASR API key not configured")
        if file is None:
            raise HTTPException(status_code=400, detail="缺少音频或文本")
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Empty audio file")
        try:
            asr_client = get_openai_client(settings.asr_base_url, asr_key)
            tr = await asr_client.audio.transcriptions.create(
                model=settings.asr_model,
                file=(file.filename or "audio.wav", data, file.content_type or "audio/wav"),
            )
            text = (getattr(tr, "text", "") or "").strip()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"ASR failed: {e}")
    if not text:
        raise HTTPException(status_code=422, detail="No speech recognized")
    t_asr = time.monotonic()

    out_q: asyncio.Queue = asyncio.Queue(maxsize=64)
    tts_q: asyncio.Queue = asyncio.Queue(maxsize=24)
    state = {"reply": "", "interrupted": False, "saved": False, "audio": 0}

    async def tts_worker():
        seq = 0
        tts_client = get_openai_client(settings.tts_base_url, tts_key)
        while True:
            sentence = await tts_q.get()
            if sentence is None:
                return
            pcm, rate = await _synthesize_voice_reply(sentence, tts_client, voice)
            if not pcm:
                continue
            pcm = trim_silence(pcm, rate)
            if not pcm:
                continue
            await out_q.put({
                "t": "audio",
                "seq": seq,
                "text": sentence,
                "rate": rate,
                "pcm": base64.b64encode(pcm).decode(),
            })
            state["audio"] += 1
            seq += 1

    async def pipeline(bot, messages):
        tts_task = asyncio.create_task(tts_worker())
        chunker = SentenceChunker()
        first_token = None
        token = set_current_bot_id(bot.id)
        session_token = set_current_session_id(sid)
        try:
            async for ev in iter_agent_events(
                run_agent_stream(
                    user["id"],
                    messages,
                    tools_filter=bot.allowed_tools,
                    max_turns=bot.max_turns or 60,
                    model=bot.model,
                    temperature=bot.temperature if bot.temperature is not None else 0.7,
                    bot=bot,
                    session_id=sid,
                )
            ):
                typ = ev.get("type")
                if typ == "token":
                    piece = ev.get("content") or ""
                    if not piece:
                        continue
                    if first_token is None:
                        first_token = time.monotonic()
                    state["reply"] += piece
                    await out_q.put({"t": "delta", "text": piece})
                    for sentence in chunker.push(piece):
                        await tts_q.put(sentence)
                elif typ in ("tool_call", "tool_result"):
                    await out_q.put({"t": "status", "text": "正在执行工具…"})

            for sentence in chunker.flush():
                await tts_q.put(sentence)
            await tts_q.put(None)
            await tts_task

            reply = state["reply"].strip() or "已执行。"
            state["saved"] = True
            await save_message(user["id"], "assistant", reply, sid, bot=bot)
            log.info(
                "[voice_turn] done sid=%s first_token=%.2fs sentences=%d total=%.2fs",
                sid,
                (first_token - t_start) if first_token else -1,
                state["audio"],
                time.monotonic() - t_start,
            )
            await out_q.put({"t": "done", "reply": reply, "interrupted": False})
        except asyncio.CancelledError:
            state["interrupted"] = True
            tts_task.cancel()
            try:
                out_q.put_nowait({
                    "t": "done",
                    "reply": state["reply"].strip(),
                    "interrupted": True,
                })
            except asyncio.QueueFull:
                pass
            raise
        except Exception as e:
            tts_task.cancel()
            log.warning("[voice_turn] failed sid=%s: %s", sid, e)
            await out_q.put({"t": "status", "text": f"处理失败：{e}"[:120]})
            await out_q.put({
                "t": "done",
                "reply": state["reply"].strip(),
                "interrupted": False,
                "error": True,
            })
        finally:
            reset_current_session_id(session_token)
            reset_current_bot_id(token)

    async def gen():
        key = f"{user['id']}:{sid}"
        prev = _voice_tasks.get(key)
        if prev and not prev.done():
            prev.cancel()
        task: asyncio.Task | None = None
        turn_bot = None
        # Emit the transcript before bot/memory setup: build_messages can take
        # over a second and must not delay the first visible result.
        yield json.dumps({"t": "transcript", "text": text}, ensure_ascii=False) + "\n"
        try:
            turn_bot = await _resolve_bot(user["id"], bot_id)
            req = ChatRequest(message=text, session_id=sid, bot_id=turn_bot.id)
            voice_system = VOICE_STYLE + await _voice_context()
            messages = await build_messages(
                req, user["id"], bot=turn_bot, extra_system=voice_system,
                history_limit=6, fast=True,
            )
            await save_message(user["id"], "user", text, sid, bot=turn_bot)
            log.info(
                "[voice_turn] sid=%s asr=%.2fs pre_agent=%.2fs text=%r",
                sid,
                t_asr - t_start,
                time.monotonic() - t_start,
                text[:40],
            )
            task = asyncio.create_task(pipeline(turn_bot, messages))
            _voice_tasks[key] = task
            while True:
                item = await out_q.get()
                yield json.dumps(item, ensure_ascii=False) + "\n"
                if item.get("t") == "done":
                    break
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("[voice_turn] setup failed sid=%s: %s", sid, e)
            yield json.dumps({"t": "done", "reply": "", "error": True}, ensure_ascii=False) + "\n"
        finally:
            if task is not None:
                if not task.done():
                    task.cancel()
                if _voice_tasks.get(key) is task:
                    _voice_tasks.pop(key, None)
            partial = state["reply"].strip()
            if not state["saved"] and partial:
                state["saved"] = True
                asyncio.create_task(
                    save_message(user["id"], "assistant", partial, sid, bot=turn_bot)
                )

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
        client = get_openai_client(settings.llm_base_url, settings.llm_api_key)
        resp = await tracked_create(client, 
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
