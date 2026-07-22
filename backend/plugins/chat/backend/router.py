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

    # Inject user context (profile + entities) as system prompt
    user_ctx = []
    try:
        from sqlalchemy import select
        from core.auth.domain.models import UserProfile
        from core.database.session import async_session
        async with async_session() as db:
            r = await db.execute(select(UserProfile).where(UserProfile.user_id == user["id"]))
            prof = r.scalar_one_or_none()
            if prof:
                parts = []
                if prof.name: parts.append(f"姓名: {prof.name}")
                if prof.role: parts.append(f"角色: {prof.role}")
                if prof.company: parts.append(f"公司: {prof.company}")
                if prof.contacts:
                    import json
                    contacts = json.loads(prof.contacts) if isinstance(prof.contacts, str) else prof.contacts
                    if contacts: parts.append(f"联系人: {'; '.join([f'{c.get(\"name\",\"\")}({c.get(\"relation\",\"\")})' for c in contacts])}")
                if prof.projects:
                    import json
                    projects = json.loads(prof.projects) if isinstance(prof.projects, str) else prof.projects
                    if projects: parts.append(f"项目: {'; '.join([f'{p.get(\"name\",\"\")}({p.get(\"deadline\",\"\")})' for p in projects])}")
                if parts:
                    user_ctx.append("【用户信息】\n" + "\n".join(parts))
    except Exception:
        pass

    # Fetch recent entities from Qdrant if memory layer enabled
    if settings.memory_layer_enabled and user_ctx:
        try:
            from qdrant_client import QdrantClient
            from core.ai.embeddings import generate_embedding
            host = settings.qdrant_url.replace("http://","").split(":")[0]
            port = int(settings.qdrant_url.split(":")[-1])
            qc = QdrantClient(host=host, port=port)
            collections = qc.get_collections().collections
            if any(c.name == "entities" for c in collections):
                vec = await generate_embedding(req.message)
                if vec:
                    hits = qc.search("entities", query_vector=vec, limit=5, query_filter={"must": [{"key": "user_id", "match": {"value": user["id"]}}]})
                    if hits:
                        related = [f"{h.payload.get('name','')}({h.payload.get('type','')})" for h in hits]
                        user_ctx.append("【相关实体】\n" + ", ".join(related))
        except Exception:
            pass

    if user_ctx:
        messages.insert(0, {"role": "system", "content": "\n\n".join(user_ctx)})

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
