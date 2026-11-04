"""Persistent bot runner.

A ``BotRun`` is the unit of work. Execution happens in a background asyncio
task, writes its state to MySQL/SQLite, and streams through polling so a
disconnected client can reconnect without losing the task.

Design notes:
- Human approval pauses the run and persists the exact messages + pending tool
  call. Approving resumes from that checkpoint.
- Cancellation is cooperative: checked before each model turn and tool call.
- Recovery marks stale ``running`` runs as failed and re-enqueues ``queued`` ones.
"""
import asyncio
import json
import time
from datetime import datetime, timedelta

from openai import AsyncOpenAI
from sqlalchemy import select, update

from core.ai.agent import _serialize_result, _to_openai_tools
from core.ai.mcp.registry import tool_registry
from core.bots import policy
from core.bots.context import (
    reset_current_bot_id,
    reset_current_run_id,
    reset_current_session_id,
    set_current_bot_id,
    set_current_run_id,
    set_current_session_id,
)
from core.bots.memory import add_memory, build_bot_context
from core.bots.models import Bot, BotApproval, BotRun, BotRunStep
from core.config.settings import settings
from core.database.session import async_session

TERMINAL = ("done", "failed", "cancelled")
MAX_TOOL_OUTPUT = 8000

_tasks: set[asyncio.Task] = set()
_active: set[int] = set()
_semaphore: asyncio.Semaphore | None = None


def _sem() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(max(1, settings.bot_run_concurrency))
    return _semaphore


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _now() -> datetime:
    return datetime.utcnow()


def enqueue_run(run_id: int) -> None:
    task = asyncio.create_task(execute_run(run_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def create_run(
    user_id: int,
    bot: Bot,
    prompt: str,
    *,
    messages: list[dict] | None = None,
    trigger: str = "api",
    routine_id: int | None = None,
    parent_run_id: int | None = None,
    session_id: str | None = None,
    idempotency_key: str | None = None,
    auto_start: bool = True,
) -> BotRun:
    async with async_session() as db:
        if idempotency_key:
            existing = (
                await db.execute(
                    select(BotRun).where(BotRun.idempotency_key == idempotency_key)
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing

        run = BotRun(
            bot_id=bot.id,
            user_id=user_id,
            routine_id=routine_id,
            parent_run_id=parent_run_id,
            session_id=session_id,
            trigger=trigger,
            status="queued",
            input=(prompt or "")[:20000],
            idempotency_key=idempotency_key,
            checkpoint={"messages": messages} if messages else None,
            heartbeat_at=_now(),
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

    if auto_start:
        enqueue_run(run.id)
    return run


async def execute_run(run_id: int) -> None:
    """Entry point used by enqueue/recovery. Safe against double-execution."""
    if run_id in _active:
        return
    _active.add(run_id)
    try:
        async with _sem():
            await _execute(run_id)
    except Exception as e:
        print(f"[bots.runner] run {run_id} crashed: {e}")
        await _finalize(run_id, "failed", error=str(e))
    finally:
        _active.discard(run_id)


async def _execute(run_id: int) -> None:
    run, bot = await _load_run_bot(run_id)
    if run is None or bot is None:
        return
    if run.status in TERMINAL:
        return

    coding = await _coding_run(run_id)
    if coding is not None:
        await _execute_coding(run, bot, coding)
        return

    checkpoint = run.checkpoint or {}
    pending = checkpoint.get("pending") or {}
    seq = int(checkpoint.get("seq") or 0)
    messages = checkpoint.get("messages")

    if run.status == "waiting_approval":
        if not pending:
            return
        approval = await _load_approval(pending.get("approval_id"))
        if approval is None or approval.status == "pending":
            return

    if not messages:
        messages = await _default_messages(run.user_id, bot, run.input or "")

    await _mark_running(run.id, run.started_at)

    if pending:
        status, seq = await _resume_pending(run, bot, messages, pending, seq)
        if status == "waiting":
            return
        await _save_checkpoint(run.id, {"messages": messages, "seq": seq})

    await _loop(run, bot, messages, seq)


async def _execute_coding(run: BotRun, bot: Bot, coding) -> None:
    from core.coding.engine import run_coding

    await _mark_running(run.id, run.started_at)
    seq = 0

    async def emit(event: str, data: dict) -> None:
        nonlocal seq
        if event == "step":
            await _add_step(
                run.id,
                seq,
                "tool",
                data.get("name"),
                data.get("arguments"),
                data.get("result"),
                data.get("status") or "ok",
            )
            seq += 1
        elif event == "delivery":
            await _add_step(
                run.id,
                seq,
                "delivery",
                None,
                None,
                f"{data.get('stage')}: {data.get('detail') or ''}",
                "ok" if data.get("ok") is not False else "error",
            )
            seq += 1
        elif event == "partial":
            await _set_partial(run.id, data.get("content") or "")
        elif event == "checkpoint":
            await _save_checkpoint(
                run.id,
                {"messages": data.get("messages") or [], "seq": seq},
            )

    async def cancelled() -> bool:
        return await _cancelled(run.id)

    result = await run_coding(
        run, bot, coding, on_event=emit, is_cancelled=cancelled
    )
    await _finalize(
        run.id,
        result.get("status") or "done",
        output=result.get("output"),
        error=result.get("error"),
        skip_summary=True,
    )


async def _loop(run: BotRun, bot: Bot, messages: list[dict], seq: int) -> None:
    client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    all_tools = tool_registry.get_tools()
    if bot.allowed_tools is not None:
        all_tools = [t for t in all_tools if t.name in bot.allowed_tools]
    tools = _to_openai_tools(all_tools)

    max_turns = min(int(bot.max_turns or settings.bot_run_max_turns), 50)
    deadline = _now() + timedelta(seconds=max(60, settings.bot_run_timeout_seconds))

    for _ in range(max_turns):
        if await _cancelled(run.id):
            await _finalize(run.id, "cancelled")
            return
        if _now() > deadline:
            await _finalize(run.id, "failed", error="run timeout")
            return
        await _heartbeat(run.id)

        try:
            content, reasoning, tool_calls = await _stream_completion(
                client, run.id, bot, messages, tools
            )
        except Exception as e:
            await _finalize(run.id, "failed", error=f"LLM error: {e}")
            return

        assistant: dict = {"role": "assistant", "content": content or None}
        if reasoning:
            assistant["reasoning_content"] = reasoning
        if tool_calls:
            assistant["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                    },
                }
                for tc in tool_calls
            ]
        messages.append(assistant)

        if not tool_calls:
            await _finalize(run.id, "done", output=content)
            return

        status, seq = await _execute_tool_calls(run, bot, messages, tool_calls, 0, seq)
        if status == "waiting":
            return
        await _save_checkpoint(run.id, {"messages": messages, "seq": seq})

    await _finalize(run.id, "failed", error=f"reached max turns ({max_turns})")


async def _stream_completion(
    client: AsyncOpenAI,
    run_id: int,
    bot: Bot,
    messages: list[dict],
    tools: list[dict],
) -> tuple[str, str, list[dict]]:
    content = ""
    reasoning = ""
    raw_calls: list[dict] | None = None
    last_partial = 0.0

    stream = await client.chat.completions.create(
        model=bot.model or settings.llm_model,
        messages=messages,
        tools=tools or None,
        temperature=bot.temperature if bot.temperature is not None else 0.7,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if not delta:
            continue

        rc = getattr(delta, "reasoning_content", None)
        if rc:
            reasoning += rc

        if delta.content:
            content += delta.content
            if time.time() - last_partial > 0.8:
                await _set_partial(run_id, content)
                last_partial = time.time()

        if delta.tool_calls:
            if raw_calls is None:
                raw_calls = [
                    {"id": "", "function": {"name": "", "arguments": ""}}
                    for _ in delta.tool_calls
                ]
            for i, tc in enumerate(delta.tool_calls):
                if tc.id:
                    raw_calls[i]["id"] += tc.id
                if tc.function:
                    if tc.function.name:
                        raw_calls[i]["function"]["name"] += tc.function.name
                    if tc.function.arguments:
                        raw_calls[i]["function"]["arguments"] += tc.function.arguments

    if content:
        await _set_partial(run_id, content)

    calls: list[dict] = []
    for tc in raw_calls or []:
        try:
            args = json.loads(tc["function"]["arguments"])
        except json.JSONDecodeError:
            args = {}
        calls.append(
            {
                "id": tc["id"] or f"call_{len(calls)}",
                "name": tc["function"]["name"],
                "arguments": args,
            }
        )
    return content, reasoning, calls


async def _execute_tool_calls(
    run: BotRun,
    bot: Bot,
    messages: list[dict],
    tool_calls: list[dict],
    start: int,
    seq: int,
) -> tuple[str, int]:
    for i in range(start, len(tool_calls)):
        tc = tool_calls[i]
        name = tc["name"]
        risk, decision = policy.decide(bot, name)

        if decision == "deny":
            text = f"工具 {name} 被当前 Bot 的策略拒绝执行。"
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": text})
            await _add_step(run.id, seq, "tool", name, tc["arguments"], text, "denied")
            seq += 1
            continue

        if decision == "ask":
            reason = f"{name} 属于 {risk} 风险级别，需要用户确认。"
            approval = await _create_approval(run, tc, risk, reason)
            await _save_checkpoint(
                run.id,
                {
                    "messages": messages,
                    "seq": seq,
                    "pending": {
                        "tool_calls": tool_calls,
                        "index": i,
                        "approval_id": approval.id,
                    },
                },
            )
            await _set_status(run.id, "waiting_approval")
            await _add_step(
                run.id, seq, "approval", name, tc["arguments"], reason, "pending"
            )
            await _notify_approval(run, approval, reason)
            return "waiting", seq

        text, is_err = await _call_tool(run, name, tc["arguments"])
        messages.append({"role": "tool", "tool_call_id": tc["id"], "content": text})
        await _add_step(
            run.id, seq, "tool", name, tc["arguments"], text, "error" if is_err else "ok"
        )
        seq += 1

    return "continue", seq


async def _resume_pending(
    run: BotRun,
    bot: Bot,
    messages: list[dict],
    pending: dict,
    seq: int,
) -> tuple[str, int]:
    approval = await _load_approval(pending.get("approval_id"))
    idx = int(pending.get("index") or 0)
    tool_calls = pending.get("tool_calls") or []
    if idx >= len(tool_calls):
        return "continue", seq

    tc = tool_calls[idx]
    if approval is not None and approval.status == "approved":
        text, is_err = await _call_tool(run, tc["name"], tc["arguments"])
        messages.append({"role": "tool", "tool_call_id": tc["id"], "content": text})
        await _add_step(
            run.id, seq, "tool", tc["name"], tc["arguments"], text,
            "error" if is_err else "ok",
        )
    else:
        reason = (approval.reason if approval is not None else "") or "用户拒绝"
        text = f"用户拒绝执行工具 {tc['name']}。原因：{reason}"
        messages.append({"role": "tool", "tool_call_id": tc["id"], "content": text})
        await _add_step(run.id, seq, "approval", tc["name"], tc["arguments"], text, "denied")
    seq += 1

    # Clear the pending marker before continuing, otherwise a crash could loop.
    await _save_checkpoint(run.id, {"messages": messages, "seq": seq})
    return await _execute_tool_calls(run, bot, messages, tool_calls, idx + 1, seq)


async def _call_tool(run: BotRun, name: str, arguments: dict) -> tuple[str, bool]:
    req = type("Req", (), {"name": name, "arguments": arguments})()
    token = set_current_bot_id(run.bot_id)
    run_token = set_current_run_id(run.id)
    session_token = set_current_session_id(run.session_id)
    try:
        result = await tool_registry.call(run.user_id, req)
    finally:
        reset_current_session_id(session_token)
        reset_current_run_id(run_token)
        reset_current_bot_id(token)
    text = _serialize_result(result)[:MAX_TOOL_OUTPUT]
    is_err = bool(getattr(result, "isError", False) or getattr(result, "is_error", False))
    return text, is_err


async def _default_messages(user_id: int, bot: Bot, prompt: str) -> list[dict]:
    messages = []
    persona = bot.system_prompt or settings.assistant_system_prompt
    if persona:
        messages.append({"role": "system", "content": persona})
    ctx = await build_bot_context(user_id, bot, prompt)
    if ctx:
        messages.append({"role": "system", "content": ctx})
    messages.append({"role": "user", "content": prompt})
    return messages


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

async def _coding_run(run_id: int):
    try:
        from core.coding.service import get_coding_run

        return await get_coding_run(run_id)
    except Exception:
        return None


async def _load_run_bot(run_id: int) -> tuple[BotRun | None, Bot | None]:
    async with async_session() as db:
        run = (
            await db.execute(select(BotRun).where(BotRun.id == run_id))
        ).scalar_one_or_none()
        if run is None:
            return None, None
        bot = (
            await db.execute(select(Bot).where(Bot.id == run.bot_id))
        ).scalar_one_or_none()
        return run, bot


async def _create_approval(
    run: BotRun, tc: dict, risk: str, reason: str
) -> BotApproval:
    async with async_session() as db:
        approval = BotApproval(
            run_id=run.id,
            bot_id=run.bot_id,
            user_id=run.user_id,
            tool_name=tc["name"],
            arguments=tc["arguments"],
            risk_level=risk,
            status="pending",
            reason=reason,
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)
        return approval


async def _load_approval(approval_id) -> BotApproval | None:
    if not approval_id:
        return None
    async with async_session() as db:
        return (
            await db.execute(
                select(BotApproval).where(BotApproval.id == int(approval_id))
            )
        ).scalar_one_or_none()


async def _mark_running(run_id: int, started_at) -> None:
    async with async_session() as db:
        await db.execute(
            update(BotRun)
            .where(BotRun.id == run_id)
            .values(
                status="running",
                started_at=started_at or _now(),
                heartbeat_at=_now(),
                error=None,
                partial=None,
            )
        )
        await db.commit()


async def _heartbeat(run_id: int) -> None:
    async with async_session() as db:
        await db.execute(
            update(BotRun).where(BotRun.id == run_id).values(heartbeat_at=_now())
        )
        await db.commit()


async def _set_partial(run_id: int, text: str) -> None:
    async with async_session() as db:
        await db.execute(
            update(BotRun).where(BotRun.id == run_id).values(partial=text)
        )
        await db.commit()


async def _set_status(run_id: int, status: str) -> None:
    async with async_session() as db:
        await db.execute(
            update(BotRun)
            .where(BotRun.id == run_id)
            .values(status=status, heartbeat_at=_now())
        )
        await db.commit()


async def _save_checkpoint(run_id: int, checkpoint: dict) -> None:
    async with async_session() as db:
        await db.execute(
            update(BotRun)
            .where(BotRun.id == run_id)
            .values(checkpoint=checkpoint, heartbeat_at=_now())
        )
        await db.commit()


async def _add_step(
    run_id: int,
    seq: int,
    type_: str,
    tool_name: str | None,
    arguments: dict | None,
    result: str | None,
    status: str,
) -> None:
    async with async_session() as db:
        db.add(
            BotRunStep(
                run_id=run_id,
                seq=seq,
                type=type_,
                tool_name=tool_name,
                arguments=arguments,
                result=(result or "")[:MAX_TOOL_OUTPUT],
                status=status,
            )
        )
        await db.commit()


async def _cancelled(run_id: int) -> bool:
    async with async_session() as db:
        status = (
            await db.execute(select(BotRun.status).where(BotRun.id == run_id))
        ).scalar_one_or_none()
        return status == "cancelled"


async def _finalize(
    run_id: int,
    status: str,
    output: str | None = None,
    error: str | None = None,
    skip_summary: bool = False,
) -> None:
    async with async_session() as db:
        run = (
            await db.execute(select(BotRun).where(BotRun.id == run_id))
        ).scalar_one_or_none()
        if run is None:
            return
        if run.status in TERMINAL:
            return
        run.status = status
        run.output = output
        run.error = error
        run.partial = None
        run.finished_at = _now()
        run.heartbeat_at = _now()
        await db.commit()
        bot = (
            await db.execute(select(Bot).where(Bot.id == run.bot_id))
        ).scalar_one_or_none()

    if status == "done":
        if run.session_id and run.output:
            await _save_chat_reply(run)
            if await _coding_run(run.id) is not None:
                await _broadcast_chat_reply(run)
        if run.routine_id and run.output:
            await _notify_run(run, bot)
        if run.output and settings.bot_run_auto_summary and not skip_summary:
            await _maybe_summarize(run, bot)


async def _broadcast_chat_reply(run: BotRun) -> None:
    """Push asynchronous replies (e.g. delegated coding runs) to open chats."""
    try:
        from core.wschannel.hub import host_channel

        await host_channel.broadcast(
            run.user_id,
            "chat",
            {
                "type": "chat_reply",
                "session_id": run.session_id,
                "bot_id": run.bot_id,
                "run_id": run.id,
                "content": run.output or "",
            },
        )
    except Exception as e:
        print(f"[bots.runner] broadcast chat reply failed: {e}")


async def _save_chat_reply(run: BotRun) -> None:
    """Append the run's final answer to the originating chat session."""
    try:
        from plugins.chat.backend.router import save_message

        async with async_session() as db:
            bot = (
                await db.execute(select(Bot).where(Bot.id == run.bot_id))
            ).scalar_one_or_none()
        await save_message(
            run.user_id, "assistant", run.output, run.session_id, bot=bot
        )
    except Exception as e:
        print(f"[bots.runner] save chat reply failed: {e}")


async def _maybe_summarize(run: BotRun, bot: Bot | None) -> None:
    """Persist one compact long-term memory after a substantive run."""
    if bot is None or not settings.memory_layer_enabled:
        return
    if not run.routine_id and len(run.output or "") < 800:
        return
    try:
        client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        resp = await client.chat.completions.create(
            model=bot.model or settings.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "把下面这次任务压缩成一条长期记忆，只保留结论、用户偏好、"
                        "未完成事项和关键事实。不超过 200 字，不要 Markdown。"
                    ),
                },
                {"role": "user", "content": (run.input or "") + "\n\n" + (run.output or "")},
            ],
            temperature=0.2,
        )
        text = (resp.choices[0].message.content or "").strip()
        if text:
            await add_memory(
                run.user_id,
                run.bot_id,
                text,
                kind="summary",
                importance=0.6,
                source_run_id=run.id,
            )
    except Exception as e:
        print(f"[bots.runner] summary failed: {e}")


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

async def _notify_run(run: BotRun, bot: Bot | None) -> None:
    title = f"🤖 {bot.name if bot else 'Bot'}"
    body = (run.output or "")[:4000]
    try:
        from plugins.notifications.backend.service import create_notification

        async with async_session() as db:
            n = await create_notification(db, run.user_id, title, body, "bot_run", "/bots?tab=runs")
            await db.commit()
            nid = n.id
        try:
            from core.wschannel.hub import host_channel

            await host_channel.broadcast(
                run.user_id,
                "notifications",
                {"type": "new_notification", "id": nid, "title": title, "body": body},
            )
        except Exception:
            pass
        try:
            from plugins.device.backend.events import publish_device_event

            await publish_device_event(
                run.user_id, "bot_run", {"id": nid, "title": title}
            )
        except Exception:
            pass
    except Exception as e:
        print(f"[bots.runner] notify failed: {e}")


async def _notify_approval(run: BotRun, approval: BotApproval, reason: str) -> None:
    title = "🔐 需要审批"
    body = f"{approval.tool_name}：{reason}"
    try:
        from plugins.notifications.backend.service import create_notification

        async with async_session() as db:
            n = await create_notification(
                db, run.user_id, title, body, "approval", "/bots?tab=approvals"
            )
            await db.commit()
            nid = n.id
        try:
            from core.wschannel.hub import host_channel

            await host_channel.broadcast(
                run.user_id,
                "notifications",
                {
                    "type": "approval_required",
                    "id": nid,
                    "approval_id": approval.id,
                    "run_id": run.id,
                    "title": title,
                    "body": body,
                },
            )
        except Exception:
            pass
    except Exception as e:
        print(f"[bots.runner] approval notify failed: {e}")


# ---------------------------------------------------------------------------
# Public queries / control
# ---------------------------------------------------------------------------

async def list_runs(user_id: int, bot_id: int | None = None, limit: int = 50) -> list[BotRun]:
    async with async_session() as db:
        q = select(BotRun).where(BotRun.user_id == user_id)
        if bot_id is not None:
            q = q.where(BotRun.bot_id == bot_id)
        q = q.order_by(BotRun.id.desc()).limit(limit)
        return list((await db.execute(q)).scalars().all())


async def get_run(user_id: int, run_id: int) -> BotRun | None:
    async with async_session() as db:
        return (
            await db.execute(
                select(BotRun).where(BotRun.id == run_id, BotRun.user_id == user_id)
            )
        ).scalar_one_or_none()


async def list_steps(run_id: int, after_id: int = 0) -> list[BotRunStep]:
    async with async_session() as db:
        q = select(BotRunStep).where(BotRunStep.run_id == run_id)
        if after_id:
            q = q.where(BotRunStep.id > after_id)
        q = q.order_by(BotRunStep.id.asc())
        return list((await db.execute(q)).scalars().all())


async def cancel_run(user_id: int, run_id: int) -> bool:
    async with async_session() as db:
        run = (
            await db.execute(
                select(BotRun).where(BotRun.id == run_id, BotRun.user_id == user_id)
            )
        ).scalar_one_or_none()
        if run is None:
            return False
        if run.status in TERMINAL:
            return True
        run.status = "cancelled"
        run.finished_at = _now()
        run.partial = None
        await db.execute(
            update(BotApproval)
            .where(BotApproval.run_id == run_id, BotApproval.status == "pending")
            .values(status="expired", decided_at=_now())
        )
        await db.commit()
    return True


async def stream_run(run_id: int, user_id: int):
    """Poll the persisted run and yield SSE frames."""
    sent = 0
    last_step = 0
    started = False
    deadline = time.time() + max(60, settings.bot_run_timeout_seconds) + 60

    while True:
        async with async_session() as db:
            run = (
                await db.execute(
                    select(BotRun).where(BotRun.id == run_id, BotRun.user_id == user_id)
                )
            ).scalar_one_or_none()
            if run is None:
                yield _sse({"type": "error", "content": "run not found"})
                return
            steps = list(
                (
                    await db.execute(
                        select(BotRunStep)
                        .where(BotRunStep.run_id == run_id, BotRunStep.id > last_step)
                        .order_by(BotRunStep.id.asc())
                    )
                ).scalars().all()
            )
            latest_approval_id = (
                await db.execute(
                    select(BotApproval.id)
                    .where(BotApproval.run_id == run_id)
                    .order_by(BotApproval.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

        if not started:
            started = True
            yield _sse(
                {
                    "type": "run_started",
                    "run_id": run.id,
                    "bot_id": run.bot_id,
                    "status": run.status,
                }
            )

        for s in steps:
            last_step = s.id
            payload = {
                "type": "approval_required" if s.type == "approval" else "tool_result",
                "step_id": s.id,
                "tool": s.tool_name,
                "arguments": s.arguments,
                "content": s.result,
                "status": s.status,
            }
            if s.type == "approval":
                payload["approval_id"] = latest_approval_id
            yield _sse(payload)

        if run.partial and len(run.partial) > sent:
            delta = run.partial[sent:]
            sent = len(run.partial)
            yield _sse({"type": "token", "content": delta})

        if run.status in TERMINAL:
            if run.output and len(run.output) > sent:
                delta = run.output[sent:]
                sent = len(run.output)
                yield _sse({"type": "token", "content": delta})
            yield _sse(
                {
                    "type": "done",
                    "status": run.status,
                    "reply": run.output or "",
                    "error": run.error,
                }
            )
            return

        if time.time() > deadline:
            yield _sse({"type": "error", "content": "stream timeout"})
            return

        await asyncio.sleep(max(0.1, settings.bot_run_poll_seconds))


async def recover_runs() -> None:
    """Startup recovery: fail stale runs, re-enqueue queued ones."""
    now = _now()
    stale = now - timedelta(seconds=max(60, settings.bot_run_heartbeat_seconds * 4))
    queued: list[int] = []

    async with async_session() as db:
        await db.execute(
            update(BotRun)
            .where(BotRun.status == "running", BotRun.heartbeat_at < stale)
            .values(status="failed", error="interrupted", finished_at=now)
        )
        old_approval_cutoff = now - timedelta(hours=24)
        waiting = list(
            (
                await db.execute(
                    select(BotRun).where(
                        BotRun.status == "waiting_approval",
                        BotRun.created_at < old_approval_cutoff,
                    )
                )
            ).scalars().all()
        )
        for run in waiting:
            run.status = "failed"
            run.error = "approval timeout"
            run.finished_at = now
            await db.execute(
                update(BotApproval)
                .where(BotApproval.run_id == run.id, BotApproval.status == "pending")
                .values(status="expired", decided_at=now)
            )
        queued = list(
            (
                await db.execute(select(BotRun.id).where(BotRun.status == "queued"))
            ).scalars().all()
        )
        await db.commit()

    for run_id in queued:
        enqueue_run(run_id)
