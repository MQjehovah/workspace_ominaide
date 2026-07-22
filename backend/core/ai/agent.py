"""Simple Agent: LLM + MCP tool loop."""
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
    """Agent loop: LLM calls MCP tools -> execute -> feed back -> final response."""
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
