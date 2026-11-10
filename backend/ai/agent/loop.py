"""Agent with streaming support."""
import json
from ai.llm.usage import record_chat_usage, tracked_create
from core.config.settings import settings
from ai.llm.clients import get_openai_client
from ai.cognition.authorization import ApprovalRequired, authorized_tool_call
from ai.mcp.gateway import select_exposed_tools
from ai.mcp.registry import tool_registry
from ai.context_window import compact_context


def _to_openai_tools(mcp_tools):
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.inputSchema,
            },
        }
        for t in mcp_tools
    ]


def _normalize_calls(raw_calls) -> list[dict]:
    calls = []
    for tc in raw_calls or []:
        try:
            args = json.loads(tc["function"]["arguments"])
        except (json.JSONDecodeError, TypeError):
            args = {}
        calls.append({
            "id": tc.get("id") or f"call_{len(calls)}",
            "name": tc["function"]["name"],
            "arguments": args,
        })
    return calls


async def _persist_approval(
    user_id: int,
    bot,
    messages: list[dict],
    calls: list[dict],
    index: int,
    exc: ApprovalRequired,
    session_id: str | None,
):
    """Create a resumable run for a chat tool call that needs approval."""
    from ai.bots import runner

    return await runner.create_approval_run(
        user_id,
        bot,
        messages=messages,
        tool_calls=calls,
        index=index,
        name=exc.name,
        arguments=exc.arguments,
        capability_key=exc.auth.capability_key,
        risk=exc.auth.risk,
        reason=exc.auth.reason,
        session_id=session_id,
    )


def _serialize_result(result) -> str:
    """Serialize an MCP tool result to a compact readable string."""
    if hasattr(result, "content"):
        parts = []
        for c in result.content or []:
            if getattr(c, "text", None):
                parts.append(c.text)
            elif getattr(c, "resource", None):
                rtext = getattr(c.resource, "text", None)
                if rtext:
                    parts.append(rtext)
        try:
            if len(parts) > 1:
                return json.dumps(parts, ensure_ascii=False)
            return parts[0] if parts else ""
        except Exception:
            pass
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception:
        return str(result)


async def run_agent(
    user_id: int,
    messages: list[dict],
    tools_filter: list[str] | None = None,
    max_turns: int = 60,
    model: str | None = None,
    temperature: float = 0.7,
    bot=None,
    session_id: str | None = None,
) -> str:
    """Non-streaming agent loop (kept for backward compat)."""
    client = get_openai_client(settings.llm_base_url, settings.llm_api_key)
    all_tools = tool_registry.get_tools(user_id=user_id)
    openai_tools = _to_openai_tools(
        select_exposed_tools(all_tools, allowed=tools_filter, user_id=user_id)
    )

    for turn in range(max_turns):
        messages = await compact_context(
            messages,
            client=client,
            model=model or settings.llm_model,
        )
        resp = await tracked_create(client, 
            model=model or settings.llm_model,
            messages=messages,
            tools=openai_tools or None,
            temperature=temperature,
        )
        choice = resp.choices[0]
        msg = choice.message

        if not msg.tool_calls:
            return msg.content or ""

        assistant = {"role": "assistant", "content": msg.content or None}
        reasoning = getattr(msg, "reasoning_content", None)
        if reasoning:
            assistant["reasoning_content"] = reasoning
        assistant["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
        messages.append(assistant)

        calls = _normalize_calls([
            {"id": tc.id, "function": {
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            }}
            for tc in msg.tool_calls
        ])
        for index, tc in enumerate(calls):
            try:
                result = await authorized_tool_call(
                    user_id,
                    tc["name"],
                    tc["arguments"],
                    bot=bot,
                    session_id=session_id,
                    raise_on_approval=True,
                )
            except ApprovalRequired as exc:
                if bot is None:
                    return (
                        f"需要你确认后才能执行 {tc['name']}，"
                        "请在审批中心处理。"
                    )
                await _persist_approval(
                    user_id, bot, messages, calls, index, exc, session_id
                )
                return (
                    f"需要你确认后才能执行 {tc['name']}。"
                    "审批通过后我会继续。"
                )
            content = _serialize_result(result)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": content,
            })

    return "Agent reached max turns without final response."


async def run_agent_stream(
    user_id: int,
    messages: list[dict],
    tools_filter: list[str] | None = None,
    max_turns: int = 60,
    model: str | None = None,
    temperature: float = 0.7,
    bot=None,
    session_id: str | None = None,
):
    """Streaming agent: yields SSE-formatted strings."""
    client = get_openai_client(settings.llm_base_url, settings.llm_api_key)
    all_tools = tool_registry.get_tools(user_id=user_id)
    openai_tools = _to_openai_tools(
        select_exposed_tools(all_tools, allowed=tools_filter, user_id=user_id)
    )

    total_chars = 0
    total_tools = 0

    def usage_event():
        return f"data: {json.dumps({'type': 'usage', 'chars': total_chars, 'tools': total_tools}, ensure_ascii=False)}\n\n"

    for turn in range(max_turns):
        messages = await compact_context(
            messages,
            client=client,
            model=model or settings.llm_model,
        )
        accumulated_content = ""
        accumulated_reasoning = ""
        tool_calls = None
        async for chunk in await tracked_create(client, 
            model=model or settings.llm_model,
            messages=messages,
            tools=openai_tools or None,
            temperature=temperature,
            stream=True,
            stream_options={"include_usage": True},
        ):
            usage = getattr(chunk, "usage", None)
            if usage:
                record_chat_usage(model or settings.llm_model, usage)
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue

            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                accumulated_reasoning += reasoning
                yield f"data: {json.dumps({'type': 'reasoning', 'content': reasoning}, ensure_ascii=False)}\n\n"

            if delta.content:
                accumulated_content += delta.content
                yield f"data: {json.dumps({'type': 'token', 'content': delta.content}, ensure_ascii=False)}\n\n"

            if delta.tool_calls:
                if tool_calls is None:
                    tool_calls = []
                for tc in delta.tool_calls:
                    idx = int(getattr(tc, "index", 0) or 0)
                    while len(tool_calls) <= idx:
                        tool_calls.append(
                            {"id": "", "function": {"name": "", "arguments": ""}}
                        )
                    slot = tool_calls[idx]
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            slot["function"]["name"] = tc.function.name
                        if tc.function.arguments:
                            slot["function"]["arguments"] += tc.function.arguments

            finish_reason = chunk.choices[0].finish_reason if chunk.choices else None
            if finish_reason == "stop":
                total_chars += len(accumulated_content) + len(accumulated_reasoning)
                yield usage_event()
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            if finish_reason == "tool_calls":
                break

        total_chars += len(accumulated_content) + len(accumulated_reasoning)
        total_tools += len(tool_calls or [])

        if not tool_calls:
            yield usage_event()
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        msg: dict = {"role": "assistant", "content": accumulated_content or None}
        # DeepSeek thinking mode: reasoning_content must be echoed back verbatim
        if accumulated_reasoning:
            msg["reasoning_content"] = accumulated_reasoning
        openai_tc = []
        for tc in tool_calls:
            try:
                func_args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                func_args = {}
            openai_tc.append({
                "id": tc["id"],
                "type": "function",
                "function": {"name": tc["function"]["name"], "arguments": json.dumps(func_args, ensure_ascii=False)},
            })
        msg["tool_calls"] = openai_tc
        messages.append(msg)

        calls = _normalize_calls(tool_calls)
        for index, call in enumerate(calls):
            name = call["name"]
            func_args = call["arguments"]
            yield f"data: {json.dumps({'type': 'tool_call', 'name': name, 'arguments': func_args}, ensure_ascii=False)}\n\n"

            try:
                result = await authorized_tool_call(
                    user_id,
                    name,
                    func_args,
                    bot=bot,
                    session_id=session_id,
                    raise_on_approval=True,
                )
            except ApprovalRequired as exc:
                if bot is None:
                    yield f"data: {json.dumps({'type': 'error', 'content': f'{name} 需要用户确认，请在审批中心处理。'}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return
                run, approval = await _persist_approval(
                    user_id, bot, messages, calls, index, exc, session_id
                )
                yield f"data: {json.dumps({'type': 'approval_required', 'run_id': run.id, 'approval_id': approval.id, 'tool': name, 'arguments': func_args, 'risk': exc.auth.risk, 'reason': exc.auth.reason}, ensure_ascii=False)}\n\n"
                yield usage_event()
                yield f"data: {json.dumps({'type': 'done', 'pending_approval': True})}\n\n"
                return
            content = _serialize_result(result)
            is_err = bool(getattr(result, "isError", False) or getattr(result, "is_error", False))
            yield f"data: {json.dumps({'type': 'tool_result', 'name': name, 'content': content, 'error': is_err}, ensure_ascii=False)}\n\n"
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})

    yield "data: " + json.dumps({
        'type': 'token', 'content': '\n\n[Agent reached max turns]'
    }) + "\n\n"
    yield usage_event()
    yield f"data: {json.dumps({'type': 'done'})}\n\n"
