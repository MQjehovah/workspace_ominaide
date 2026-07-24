"""Agent with streaming support."""
import json
from openai import AsyncOpenAI
from core.config.settings import settings
from core.ai.mcp.registry import tool_registry


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


async def run_agent(
    user_id: int,
    messages: list[dict],
    tools_filter: list[str] | None = None,
    max_turns: int = 8,
) -> str:
    """Non-streaming agent loop (kept for backward compat)."""
    client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    all_tools = tool_registry.get_tools()
    if tools_filter:
        all_tools = [t for t in all_tools if t.name in tools_filter]
    openai_tools = _to_openai_tools(all_tools)

    for turn in range(max_turns):
        resp = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            tools=openai_tools or None,
            temperature=0.7,
        )
        choice = resp.choices[0]
        msg = choice.message

        if not msg.tool_calls:
            return msg.content or ""

        messages.append(msg)
        for tc in msg.tool_calls:
            try:
                func_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                func_args = {}
            result = await tool_registry.call(
                user_id,
                type("Req", (), {"name": tc.function.name, "arguments": func_args})(),
            )
            content = json.dumps(result.data, ensure_ascii=False) if hasattr(result, "data") else str(result)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})

    return "Agent reached max turns without final response."


async def run_agent_stream(
    user_id: int,
    messages: list[dict],
    tools_filter: list[str] | None = None,
    max_turns: int = 8,
):
    """Streaming agent: yields SSE-formatted strings."""
    client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    all_tools = tool_registry.get_tools()
    if tools_filter:
        all_tools = [t for t in all_tools if t.name in tools_filter]
    openai_tools = _to_openai_tools(all_tools)

    for turn in range(max_turns):
        accumulated_content = ""
        tool_calls = None
        async for chunk in await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            tools=openai_tools or None,
            temperature=0.7,
            stream=True,
        ):
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue

            if delta.content:
                accumulated_content += delta.content
                yield f"data: {json.dumps({'type': 'token', 'content': delta.content}, ensure_ascii=False)}\n\n"

            if delta.tool_calls:
                if tool_calls is None:
                    tool_calls = [{"id": "", "function": {"name": "", "arguments": ""}} for _ in delta.tool_calls]
                for i, tc in enumerate(delta.tool_calls):
                    if tc.id:
                        tool_calls[i]["id"] += tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls[i]["function"]["name"] += tc.function.name
                        if tc.function.arguments:
                            tool_calls[i]["function"]["arguments"] += tc.function.arguments

            finish_reason = chunk.choices[0].finish_reason if chunk.choices else None
            if finish_reason == "stop":
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            if finish_reason == "tool_calls":
                break

        if not tool_calls:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        msg = {"role": "assistant", "content": accumulated_content or None}
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

        for tc in tool_calls:
            try:
                func_args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                func_args = {}
            name = tc["function"]["name"]
            yield f"data: {json.dumps({'type': 'tool_call', 'name': name, 'arguments': func_args}, ensure_ascii=False)}\n\n"

            result = await tool_registry.call(
                user_id,
                type("Req", (), {"name": name, "arguments": func_args})(),
            )
            content = json.dumps(result.data, ensure_ascii=False) if hasattr(result, "data") else str(result)
            yield f"data: {json.dumps({'type': 'tool_result', 'name': name, 'content': content}, ensure_ascii=False)}\n\n"
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": content})

    yield f"data: {json.dumps({'type': 'token', 'content': '\n\n[Agent reached max turns]'})}\n\n"
    yield f"data: {json.dumps({'type': 'done'})}\n\n"
