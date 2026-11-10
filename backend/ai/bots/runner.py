"""Persistent bot runner.

A ``Run`` is the unit of work. Execution happens in a background asyncio
task, writes its state to MySQL/SQLite, and streams through polling so a
disconnected client can reconnect without losing the task.

Design notes:
- Human approval pauses the run and persists the exact messages + pending tool
  call. Approving resumes from that checkpoint.
- Cancellation is cooperative: checked before each model turn and tool call.
- Recovery marks stale ``running`` runs as failed and re-enqueues ``queued`` ones.
"""

from core.logging import get_logger
log = get_logger(__name__)
from ai.llm.usage import record_chat_usage, tracked_create
import asyncio
import json
import time
from datetime import datetime, timedelta

from openai import AsyncOpenAI
from sqlalchemy import select, update

from ai.agent.loop import _serialize_result, _to_openai_tools
from ai.mcp.gateway import (
    display_target,
    gateway_instruction,
    select_exposed_tools,
)
from ai.mcp.registry import tool_registry
from ai.cognition.authorization import authorize
from ai.bots.context import (
    reset_current_bot_id,
    reset_current_run_id,
    reset_current_session_id,
    set_current_bot_id,
    set_current_run_id,
    set_current_session_id,
)
from ai.bots.memory import build_bot_context
from ai.bots.models import Bot, Approval, Run, RunStep
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
    goal_id: int | None = None,
    task_id: int | None = None,
    agent_profile_key: str | None = None,
    agent: str | None = None,
    meta: dict | None = None,
    parent_run_id: int | None = None,
    session_id: str | None = None,
    idempotency_key: str | None = None,
    auto_start: bool = True,
) -> Run:
    async with async_session() as db:
        if idempotency_key:
            existing = (
                await db.execute(
                    select(Run).where(Run.idempotency_key == idempotency_key)
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing

        run = Run(
            bot_id=bot.id,
            user_id=user_id,
            routine_id=routine_id,
            goal_id=goal_id,
            task_id=task_id,
            agent_profile_key=agent_profile_key,
            agent=agent,
            meta=meta or {},
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


async def create_approval_run(
    user_id: int,
    bot: Bot,
    *,
    messages: list[dict],
    tool_calls: list[dict],
    index: int,
    name: str,
    arguments: dict,
    capability_key: str,
    risk: str,
    reason: str,
    session_id: str | None = None,
    goal_id: int | None = None,
    task_id: int | None = None,
    agent_profile_key: str | None = None,
) -> tuple[Run, Approval]:
    """Persist a chat tool call that needs approval as a resumable Run.

    Approving the returned approval enqueues the run; ``_execute`` resumes from
    the checkpoint, executes the tool call, and finishes the chat answer.
    """
    prompt = ""
    for item in reversed(messages):
        if item.get("role") == "user" and item.get("content"):
            prompt = str(item["content"])
            break

    async with async_session() as db:
        run = Run(
            bot_id=bot.id,
            user_id=user_id,
            goal_id=goal_id,
            task_id=task_id,
            agent_profile_key=agent_profile_key,
            session_id=session_id,
            trigger="chat",
            status="waiting_approval",
            input=prompt[:20000],
            checkpoint={
                "messages": messages,
                "seq": 0,
                "pending": {
                    "tool_calls": tool_calls,
                    "index": index,
                    "approval_id": None,
                },
            },
            heartbeat_at=_now(),
        )
        db.add(run)
        await db.flush()

        approval = Approval(
            run_id=run.id,
            bot_id=run.bot_id,
            user_id=user_id,
            tool_name=name,
            capability_key=capability_key,
            arguments=arguments,
            risk_level=risk,
            status="pending",
            reason=reason,
        )
        db.add(approval)
        await db.flush()

        checkpoint = dict(run.checkpoint)
        checkpoint["pending"] = {
            "tool_calls": tool_calls,
            "index": index,
            "approval_id": approval.id,
        }
        run.checkpoint = checkpoint
        db.add(RunStep(
            run_id=run.id,
            seq=0,
            type="approval",
            tool_name=name,
            arguments=arguments,
            result=reason,
            status="pending",
        ))
        await db.commit()
        await db.refresh(run)
        await db.refresh(approval)

    await _notify_approval(run, approval, reason)
    return run, approval


async def execute_run(run_id: int) -> None:
    """Entry point used by enqueue/recovery. Safe against double-execution."""
    if run_id in _active:
        return
    _active.add(run_id)
    try:
        async with _sem():
            await _execute(run_id)
    except Exception as e:
        log.warning(f"[bots.runner] run {run_id} crashed: {e}")
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
        await _coding_loop(run, bot, coding)
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
        messages = await _default_messages(
            run.user_id,
            bot,
            run.input or "",
            run.agent_profile_key,
            goal_id=run.goal_id,
            task_id=run.task_id,
        )

    await _mark_running(run.id, run.started_at)

    if pending:
        status, seq = await _resume_pending(run, bot, messages, pending, seq)
        if status == "waiting":
            return
        await _save_checkpoint(run.id, {"messages": messages, "seq": seq})

    await _loop(run, bot, messages, seq)


async def _coding_loop(run: Run, bot: Bot, coding) -> None:
    engine = str(getattr(coding, "engine", "") or settings.coding_engine or "builtin").lower()
    if engine == "opencode":
        from ai.coding.opencode import run_opencode as run_agent
    elif engine == "builtin":
        from ai.coding.loop import run_coding as run_agent
    else:
        await _finalize(run.id, "failed", error=f"unsupported coding engine: {engine}")
        return

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

    from ai.bots.context import (
        reset_current_bot_id,
        reset_current_run_id,
        reset_current_session_id,
        set_current_bot_id,
        set_current_run_id,
        set_current_session_id,
    )

    bot_token = set_current_bot_id(bot.id)
    run_token = set_current_run_id(run.id)
    session_token = set_current_session_id(run.session_id)
    try:
        result = await run_agent(
            run, bot, coding, on_event=emit, is_cancelled=cancelled
        )
    finally:
        reset_current_session_id(session_token)
        reset_current_run_id(run_token)
        reset_current_bot_id(bot_token)

    await _finalize(
        run.id,
        result.get("status") or "done",
        output=result.get("output"),
        error=result.get("error"),
        skip_summary=True,
    )


async def _loop(run: Run, bot: Bot, messages: list[dict], seq: int) -> None:
    from ai.bots.context import set_current_client_kind

    meta = run.meta or {}
    set_current_client_kind(str(meta.get("client_kind") or "desktop"))

    client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    all_tools = tool_registry.get_tools(user_id=run.user_id)
    from ai.cognition.agent_profiles import get_profile, scoped_tools

    profile = get_profile(run.agent_profile_key)
    tools = _to_openai_tools(
        select_exposed_tools(
            all_tools,
            bot,
            allowed=scoped_tools(bot, profile) if profile is not None else None,
        )
    )

    max_turns = min(int(bot.max_turns or settings.bot_run_max_turns), 100)
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

    stream = await tracked_create(client, 
        model=bot.model or settings.llm_model,
        messages=messages,
        tools=tools or None,
        temperature=bot.temperature if bot.temperature is not None else 0.7,
        stream=True,
        stream_options={"include_usage": True},
    )
    async for chunk in stream:
        usage = getattr(chunk, "usage", None)
        if usage:
            record_chat_usage(bot.model or settings.llm_model, usage)
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
                raw_calls = []
            for tc in delta.tool_calls:
                idx = int(getattr(tc, "index", 0) or 0)
                while len(raw_calls) <= idx:
                    raw_calls.append(
                        {"id": "", "function": {"name": "", "arguments": ""}}
                    )
                slot = raw_calls[idx]
                if tc.id:
                    slot["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        slot["function"]["name"] = tc.function.name
                    if tc.function.arguments:
                        slot["function"]["arguments"] += tc.function.arguments

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
    run: Run,
    bot: Bot,
    messages: list[dict],
    tool_calls: list[dict],
    start: int,
    seq: int,
) -> tuple[str, int]:
    for i in range(start, len(tool_calls)):
        tc = tool_calls[i]
        name = tc["name"]
        display_name, display_args = display_target(name, tc["arguments"])
        auth = await authorize(
            run.user_id,
            name,
            tc["arguments"],
            bot=bot,
            goal_id=run.goal_id,
            session_id=run.session_id,
            run_id=run.id,
            agent_profile_key=run.agent_profile_key,
        )
        risk = auth.risk
        decision = (
            "deny" if auth.decision == "deny"
            else "ask" if auth.requires_approval
            else "auto"
        )

        if decision == "deny":
            text = f"工具 {display_name} 被当前 Bot 的策略拒绝执行。"
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": text})
            await _add_step(run.id, seq, "tool", display_name, display_args, text, "denied")
            seq += 1
            continue

        if decision == "ask":
            reason = auth.reason or f"{display_name} 属于 {risk} 风险级别，需要用户确认。"
            approval = await _create_approval(
                run,
                {"id": tc["id"], "name": display_name, "arguments": display_args},
                risk,
                reason,
                capability_key=auth.capability_key,
            )
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
                run.id, seq, "approval", display_name, display_args, reason, "pending"
            )
            await _notify_approval(run, approval, reason)
            return "waiting", seq

        step_id = await _add_step(
            run.id, seq, "tool", display_name, display_args, "", "running"
        )
        text, is_err = await _call_tool(run, name, tc["arguments"])
        if auth.grant is not None and auth.grant.scope == "once" and not is_err:
            from ai.cognition.authorization import consume_grant

            await consume_grant(auth.grant.id)
        messages.append({"role": "tool", "tool_call_id": tc["id"], "content": text})
        await _update_step(
            step_id, result=text, status="error" if is_err else "ok"
        )
        seq += 1

    return "continue", seq


async def _resume_pending(
    run: Run,
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
    display_name, display_args = display_target(tc["name"], tc["arguments"])
    if approval is not None and approval.status == "approved":
        step_id = await _add_step(
            run.id, seq, "tool", display_name, display_args, "", "running"
        )
        text, is_err = await _call_tool(run, tc["name"], tc["arguments"])
        messages.append({"role": "tool", "tool_call_id": tc["id"], "content": text})
        await _update_step(
            step_id, result=text, status="error" if is_err else "ok"
        )
    else:
        reason = (approval.reason if approval is not None else "") or "用户拒绝"
        text = f"用户拒绝执行工具 {display_name}。原因：{reason}"
        messages.append({"role": "tool", "tool_call_id": tc["id"], "content": text})
        await _add_step(run.id, seq, "approval", display_name, display_args, text, "denied")
    seq += 1

    # Clear the pending marker before continuing, otherwise a crash could loop.
    await _save_checkpoint(run.id, {"messages": messages, "seq": seq})
    return await _execute_tool_calls(run, bot, messages, tool_calls, idx + 1, seq)


async def _call_tool(run: Run, name: str, arguments: dict) -> tuple[str, bool]:
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


async def _goal_task_context(user_id: int, goal_id: int | None, task_id: int | None) -> str:
    if not goal_id and not task_id:
        return ""
    try:
        from ai.cognition import goals as goal_service

        goal = await goal_service.get_goal(user_id, goal_id) if goal_id else None
        task = await goal_service.get_task(user_id, task_id) if task_id else None
        lines: list[str] = []
        if goal:
            lines.append(f"目标：{goal.get('title') or ''}")
            if goal.get("description"):
                lines.append(f"目标说明：{goal.get('description')}")
            if goal.get("success_criteria"):
                lines.append(f"目标验收：{goal.get('success_criteria')}")
        if task:
            lines.append(f"当前 Task：{task.get('title') or ''}")
            if task.get("description"):
                lines.append(f"Task 说明：{task.get('description')}")
            if task.get("acceptance"):
                lines.append(f"Task 验收：{task.get('acceptance')}")
            depends_on = task.get("depends_on") or []
            if depends_on and goal_id:
                all_tasks = await goal_service.list_tasks(user_id, goal_id)
                by_id = {item["id"]: item for item in all_tasks}
                for dep_id in depends_on:
                    dep = by_id.get(int(dep_id))
                    if not dep:
                        continue
                    output = str(dep.get("output") or "").strip()
                    if output:
                        lines.append(
                            f"前置 Task「{dep.get('title')}」结果：\n{output[:2500]}"
                        )
        if not lines:
            return ""
        lines.append("只完成当前 Task，不要越界执行其他 Task；完成后汇报结果和依据。")
        return "\n".join(lines)[:6000]
    except Exception:
        return ""


async def _default_messages(
    user_id: int,
    bot: Bot,
    prompt: str,
    agent_profile_key: str | None = None,
    *,
    goal_id: int | None = None,
    task_id: int | None = None,
) -> list[dict]:
    from ai.context_builder import ContextBuilder

    builder = ContextBuilder()
    persona = bot.system_prompt or settings.assistant_system_prompt
    if persona:
        builder.section("persona", persona, priority=100, required=True)
    if agent_profile_key:
        from ai.cognition.agent_profiles import get_profile

        profile = get_profile(agent_profile_key)
        if profile is not None:
            builder.section(
                "agent_profile",
                profile.system_prompt,
                priority=95,
                required=True,
            )
    goal_context = await _goal_task_context(user_id, goal_id, task_id)
    if goal_context:
        builder.section(
            "goal_task",
            goal_context,
            priority=92,
            required=True,
        )
    instruction = gateway_instruction()
    if instruction:
        builder.section("tool_gateway", instruction, priority=80, max_chars=4000)
    ctx = await build_bot_context(user_id, bot, prompt)
    if ctx:
        builder.section("memory", ctx, priority=55, max_chars=12000)
    from ai.skills.runtime import build_skill_context

    skill_ctx = await build_skill_context(bot)
    if skill_ctx:
        builder.section("skills", skill_ctx, priority=50, max_chars=4000)
    builder.user(prompt)
    return await builder.build()


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

async def _coding_run(run_id: int):
    try:
        from ai.coding.service import get_coding_run

        return await get_coding_run(run_id)
    except Exception:
        return None


async def _load_run_bot(run_id: int) -> tuple[Run | None, Bot | None]:
    async with async_session() as db:
        run = (
            await db.execute(select(Run).where(Run.id == run_id))
        ).scalar_one_or_none()
        if run is None:
            return None, None
        bot = (
            await db.execute(select(Bot).where(Bot.id == run.bot_id))
        ).scalar_one_or_none()
        return run, bot


async def _create_approval(
    run: Run,
    tc: dict,
    risk: str,
    reason: str,
    *,
    capability_key: str | None = None,
) -> Approval:
    async with async_session() as db:
        approval = Approval(
            run_id=run.id,
            bot_id=run.bot_id,
            user_id=run.user_id,
            tool_name=tc["name"],
            capability_key=capability_key,
            arguments=tc["arguments"],
            risk_level=risk,
            status="pending",
            reason=reason,
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)
        return approval


async def _load_approval(approval_id) -> Approval | None:
    if not approval_id:
        return None
    async with async_session() as db:
        return (
            await db.execute(
                select(Approval).where(Approval.id == int(approval_id))
            )
        ).scalar_one_or_none()


async def _mark_running(run_id: int, started_at) -> None:
    async with async_session() as db:
        await db.execute(
            update(Run)
            .where(Run.id == run_id)
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
            update(Run).where(Run.id == run_id).values(heartbeat_at=_now())
        )
        await db.commit()


async def _set_partial(run_id: int, text: str) -> None:
    async with async_session() as db:
        await db.execute(
            update(Run).where(Run.id == run_id).values(partial=text)
        )
        await db.commit()


async def _set_status(run_id: int, status: str) -> None:
    async with async_session() as db:
        await db.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(status=status, heartbeat_at=_now())
        )
        await db.commit()


async def _save_checkpoint(run_id: int, checkpoint: dict) -> None:
    async with async_session() as db:
        await db.execute(
            update(Run)
            .where(Run.id == run_id)
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
) -> int:
    async with async_session() as db:
        row = RunStep(
            run_id=run_id,
            seq=seq,
            type=type_,
            tool_name=tool_name,
            arguments=arguments,
            result=(result or "")[:MAX_TOOL_OUTPUT],
            status=status,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row.id


async def _update_step(
    step_id: int,
    *,
    result: str | None = None,
    status: str = "ok",
) -> None:
    async with async_session() as db:
        row = await db.get(RunStep, step_id)
        if row is None:
            return
        if result is not None:
            row.result = result[:MAX_TOOL_OUTPUT]
        row.status = status
        await db.commit()


async def _cancelled(run_id: int) -> bool:
    async with async_session() as db:
        status = (
            await db.execute(select(Run.status).where(Run.id == run_id))
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
            await db.execute(select(Run).where(Run.id == run_id))
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

    if run.session_id:
        try:
            from core.sessions.service import set_active_run

            await set_active_run(run.user_id, run.session_id, None)
        except Exception as e:
            log.debug("[sessions] clear active run failed: %s", e)

    if status == "done":
        if run.session_id and run.output:
            await _save_chat_reply(run)
            if run.trigger == "chat" or await _coding_run(run.id) is not None:
                await _broadcast_chat_reply(run)
        # Routines never auto-notify: the model must call send_notification
        # when it decides the user should be interrupted.
        # Emit an event instead of spending an LLM call inline. A Bot routine
        # can subscribe to bot.run.finished to summarise / persist the result.
        if run.output and run.routine_id is None and not skip_summary:
            await _emit_run_finished(run)

    if run.task_id and run.goal_id:
        asyncio.create_task(
            _after_goal_run(run.user_id, run.goal_id, run.task_id, status, run.error)
        )


async def _after_goal_run(
    user_id: int,
    goal_id: int,
    task_id: int,
    status: str,
    error: str | None,
) -> None:
    """Verify a finished goal task and let the orchestrator dispatch the next one."""
    try:
        from ai.cognition import goals as goal_service

        task = await goal_service.get_task(user_id, task_id)
        if task is None or task.get("status") not in ("running", "waiting_approval"):
            return
        if status == "done":
            from ai.cognition.verifier import verify_task

            await verify_task(user_id, task_id)
        else:
            await goal_service.update_task(
                user_id,
                task_id,
                status="failed",
                output={"error": error or f"run {status}"},
            )
            await goal_service.update_goal(user_id, goal_id, status="blocked")
            return
        from ai.cognition.orchestrator import tick_goal

        await tick_goal(user_id, goal_id)
    except Exception as exc:
        log.warning(f"[bots.runner] goal continuation failed: {exc}")


async def _broadcast_chat_reply(run: Run) -> None:
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
        log.warning(f"[bots.runner] broadcast chat reply failed: {e}")


async def _save_chat_reply(run: Run) -> None:
    """Append the run's final answer to the originating chat session."""
    try:
        from plugins.chat.backend.router import save_message

        async with async_session() as db:
            bot = (
                await db.execute(select(Bot).where(Bot.id == run.bot_id))
            ).scalar_one_or_none()
        await save_message(
            run.user_id,
            "assistant",
            run.output,
            run.session_id,
            bot=bot,
            run_id=run.id,
        )
    except Exception as e:
        log.warning(f"[bots.runner] save chat reply failed: {e}")


async def _emit_run_finished(run: Run) -> None:
    """Publish bot.run.finished so an event-triggered routine can summarise it."""
    try:
        from core.events.bus import record_event

        status = run.status or "finished"
        prefix = "Bot 运行失败" if status == "failed" else "Bot 运行完成"
        async with async_session() as db:
            await record_event(
                db, run.user_id, "bot.run.finished", "bot_run", run.id,
                f"{prefix}: {(run.input or '')[:80]}",
                {
                    "run_id": run.id,
                    "bot_id": run.bot_id,
                    "routine_id": run.routine_id,
                    "trigger": run.trigger,
                    "status": status,
                    "input": (run.input or "")[:1000],
                    "output": (run.output or "")[:4000],
                    "error": (run.error or "")[:1000] or None,
                    "tokens_in": run.tokens_in or 0,
                    "tokens_out": run.tokens_out or 0,
                    "started_at": run.started_at.isoformat() if run.started_at else None,
                    "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                },
            )
            await db.commit()
    except Exception as e:
        log.warning(f"[bots.runner] run-finished event failed: {e}")


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

async def _notify_approval(run: Run, approval: Approval, reason: str) -> None:
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
        log.warning(f"[bots.runner] approval notify failed: {e}")


# ---------------------------------------------------------------------------
# Public queries / control
# ---------------------------------------------------------------------------

async def list_runs(user_id: int, bot_id: int | None = None, limit: int = 50) -> list[Run]:
    async with async_session() as db:
        q = select(Run).where(Run.user_id == user_id)
        if bot_id is not None:
            q = q.where(Run.bot_id == bot_id)
        q = q.order_by(Run.id.desc()).limit(limit)
        return list((await db.execute(q)).scalars().all())


async def get_run(user_id: int, run_id: int) -> Run | None:
    async with async_session() as db:
        return (
            await db.execute(
                select(Run).where(Run.id == run_id, Run.user_id == user_id)
            )
        ).scalar_one_or_none()


async def list_steps(run_id: int, after_id: int = 0) -> list[RunStep]:
    async with async_session() as db:
        q = select(RunStep).where(RunStep.run_id == run_id)
        if after_id:
            q = q.where(RunStep.id > after_id)
        q = q.order_by(RunStep.id.asc())
        return list((await db.execute(q)).scalars().all())


async def cancel_run(user_id: int, run_id: int) -> bool:
    async with async_session() as db:
        run = (
            await db.execute(
                select(Run).where(Run.id == run_id, Run.user_id == user_id)
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
            update(Approval)
            .where(Approval.run_id == run_id, Approval.status == "pending")
            .values(status="expired", decided_at=_now())
        )
        await db.commit()
    return True


async def stream_run(run_id: int, user_id: int):
    """Poll the persisted run and yield SSE frames.

    SSE is intentionally stateless: the frontend can reconnect with the same
    run id and receive the current steps plus any new output. Step updates
    (``running`` -> ``ok``) are emitted by comparing the persisted snapshot.
    """
    seen_steps: dict[int, tuple] = {}
    sent_partial = 0
    sent_output = 0
    last_status = ""
    last_approval = ""
    last_ping = 0.0
    started = False
    deadline = time.time() + max(60, settings.bot_run_timeout_seconds) + 60

    while True:
        async with async_session() as db:
            run = (
                await db.execute(
                    select(Run).where(Run.id == run_id, Run.user_id == user_id)
                )
            ).scalar_one_or_none()
            if run is None:
                yield _sse({"type": "error", "content": "run not found"})
                return
            steps = list(
                (
                    await db.execute(
                        select(RunStep)
                        .where(RunStep.run_id == run_id)
                        .order_by(RunStep.id.asc())
                    )
                ).scalars().all()
            )
            latest_approval_id = (
                await db.execute(
                    select(Approval.id)
                    .where(Approval.run_id == run_id)
                    .order_by(Approval.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            pending_approval = (
                await db.execute(
                    select(Approval)
                    .where(
                        Approval.run_id == run_id,
                        Approval.status == "pending",
                    )
                    .order_by(Approval.id.desc())
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
                    "trigger": run.trigger,
                    "created_at": run.created_at.isoformat() if run.created_at else None,
                }
            )
            last_status = run.status
        elif run.status != last_status:
            last_status = run.status
            yield _sse({"type": "run_status", "status": run.status})

        for s in steps:
            signature = (
                s.status,
                s.result or "",
                s.arguments or {},
                s.tool_name,
                s.updated_at.isoformat() if getattr(s, "updated_at", None) else None,
            )
            if seen_steps.get(s.id) == signature:
                continue
            seen_steps[s.id] = signature
            payload = {
                "type": "step",
                "step_id": s.id,
                "seq": s.seq,
                "step_type": s.type,
                "tool": s.tool_name,
                "arguments": s.arguments,
                "content": s.result,
                "status": s.status,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            if s.type == "approval" and s.status == "pending" and latest_approval_id:
                payload["approval_id"] = latest_approval_id
            yield _sse(payload)

        if run.partial and len(run.partial) > sent_partial:
            delta = run.partial[sent_partial:]
            sent_partial = len(run.partial)
            yield _sse({"type": "token", "content": delta})

        if pending_approval is not None:
            signature = f"{pending_approval.id}:{pending_approval.status}"
            if signature != last_approval:
                last_approval = signature
                yield _sse({
                    "type": "approval",
                    "approval_id": pending_approval.id,
                    "run_id": run.id,
                    "tool": pending_approval.tool_name,
                    "arguments": pending_approval.arguments,
                    "risk": pending_approval.risk_level,
                    "reason": pending_approval.reason,
                    "status": pending_approval.status,
                })

        if run.status in TERMINAL:
            if run.output and len(run.output) > sent_output:
                delta = run.output[sent_output:]
                sent_output = len(run.output)
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

        now = time.time()
        if now - last_ping > 15:
            last_ping = now
            yield _sse({"type": "ping", "ts": int(now)})

        if now > deadline:
            yield _sse({"type": "error", "content": "stream timeout"})
            return

        await asyncio.sleep(max(0.1, settings.bot_run_poll_seconds))


async def recover_runs() -> None:
    """Startup recovery: fail orphaned runs and re-enqueue queued ones."""
    now = _now()
    queued: list[int] = []

    async with async_session() as db:
        # This deployment has a single backend process. Any run still marked
        # running at startup lost its worker, even if its heartbeat is recent.
        await db.execute(
            update(Run)
            .where(Run.status == "running")
            .values(
                status="failed",
                error="interrupted by backend restart; please retry",
                finished_at=now,
            )
        )
        old_approval_cutoff = now - timedelta(hours=24)
        waiting = list(
            (
                await db.execute(
                    select(Run).where(
                        Run.status == "waiting_approval",
                        Run.created_at < old_approval_cutoff,
                    )
                )
            ).scalars().all()
        )
        for run in waiting:
            run.status = "failed"
            run.error = "approval timeout"
            run.finished_at = now
            await db.execute(
                update(Approval)
                .where(Approval.run_id == run.id, Approval.status == "pending")
                .values(status="expired", decided_at=now)
            )
        queued = list(
            (
                await db.execute(select(Run.id).where(Run.status == "queued"))
            ).scalars().all()
        )
        await db.commit()

    for run_id in queued:
        enqueue_run(run_id)
