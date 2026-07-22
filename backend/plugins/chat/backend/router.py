from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI
from core.config.settings import settings
from core.auth.dependencies import get_current_user
from core.mcp.registry import tool_registry
from plugins.chat.backend.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    if not settings.llm_api_key:
        raise HTTPException(status_code=400, detail="LLM API key not configured")

    messages = []
    if req.history:
        for m in req.history:
            messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": req.message})

    # Convert MCP tools to OpenAI tool format
    mcp_tools = tool_registry.get_tools()
    openai_tools = [
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

    client = AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )

    try:
        resp = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            tools=openai_tools if openai_tools else None,
            temperature=0.7,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    choice = resp.choices[0]
    msg = choice.message

    # If the LLM wants to call tools
    if msg.tool_calls:
        import json
        messages.append(msg)
        for tc in msg.tool_calls:
            func_name = tc.function.name
            try:
                func_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                func_args = {}
            result = await tool_registry.call(user["id"], type("Req", (), {"name": func_name, "arguments": func_args})())
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result.data, ensure_ascii=False) if hasattr(result, "data") else str(result),
            })

        final_resp = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=0.7,
        )
        reply = final_resp.choices[0].message.content or ""
        return ChatResponse(reply=reply)

    reply = msg.content or ""
    return ChatResponse(reply=reply)
