import asyncio
import logging
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth.dependencies import get_current_user
from core.config.settings import settings
from core.wschannel.hub import host_channel

from plugins.vibecoding.backend.service import CHANNEL, hub

log = logging.getLogger("uvicorn")

router = APIRouter(prefix="/api/vibecoding", tags=["vibecoding"])


def register_host_channel():
    """Attach the vibecoding protocol to the shared host channel."""
    hub.register()


@router.get("/devices")
async def list_devices(user: dict = Depends(get_current_user)):
    return {"devices": hub.devices_payload(user["id"])}


@router.get("/tasks")
async def list_tasks(limit: int = 50, user: dict = Depends(get_current_user)):
    return {"tasks": hub.recent_tasks(user["id"], limit)}


@router.get("/projects")
async def list_projects(user: dict = Depends(get_current_user)):
    from plugins.vibecoding.backend.workspace import list_projects as list_workspace_projects
    return {
        "projects": list_workspace_projects(settings.coding_workspace_root),
        "tools": {"omniaide": True},
    }


class AgentStepRequest(BaseModel):
    messages: list[dict]
    tools: list[dict] = []


class AgentStepResponse(BaseModel):
    content: str | None = None
    reasoning_content: str | None = None
    tool_calls: list[dict] = []
    finish_reason: str | None = None


@router.post("/agent/step", response_model=AgentStepResponse)
async def agent_step(req: AgentStepRequest, user: dict = Depends(get_current_user)):
    if not settings.llm_api_key:
        raise HTTPException(status_code=400, detail="LLM API key not configured")
    if not req.messages or len(req.messages) > 400:
        raise HTTPException(status_code=400, detail="messages required (max 400)")
    if len(req.tools) > 32:
        raise HTTPException(status_code=400, detail="too many tools (max 32)")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    try:
        resp = await client.chat.completions.create(
            model=settings.llm_model,
            messages=req.messages,
            tools=req.tools or None,
            temperature=0.2,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM step failed: {e}")

    choice = resp.choices[0]
    msg = choice.message
    tool_calls = [
        {
            "id": tc.id,
            "type": "function",
            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
        }
        for tc in (msg.tool_calls or [])
    ]
    return AgentStepResponse(
        content=msg.content,
        reasoning_content=getattr(msg, "reasoning_content", None),
        tool_calls=tool_calls,
        finish_reason=choice.finish_reason,
    )


class CodingTaskRequest(BaseModel):
    project: str
    input: str
    tool: str = "omniaide"
    device_id: str | None = None
    source: str = "api"
    engine: str | None = None


@router.post("/tasks")
async def create_task(req: CodingTaskRequest, user: dict = Depends(get_current_user)):
    if not req.project.strip() or not req.input.strip():
        raise HTTPException(status_code=400, detail="project and input are required")
    task_id = f"t-{int(time.time() * 1000):x}-{secrets.token_hex(3)}"
    if req.tool in ("omniaide", "server") or req.engine == "server":
        from plugins.vibecoding.backend.server_agent import start_server_task
        await start_server_task(user["id"], task_id, req.project, req.input, req.source)
        return {"task_id": task_id, "dispatched": 1, "engine": "server"}
    dispatch = {
        "type": "task.dispatch",
        "task_id": task_id,
        "tool": req.tool,
        "project": req.project,
        "input": req.input,
        "source": req.source,
    }
    if req.device_id:
        sent = 1 if await host_channel.send_to_host(user["id"], req.device_id, CHANNEL, dispatch) else 0
    else:
        sent = await host_channel.broadcast_to_hosts(user["id"], CHANNEL, dispatch)
    if not sent:
        raise HTTPException(status_code=409, detail="没有在线的桌面设备")
    return {"task_id": task_id, "dispatched": sent}
