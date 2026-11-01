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
async def list_tasks(limit: int = 50, project: str | None = None,
                     user: dict = Depends(get_current_user)):
    from plugins.vibecoding.backend import store

    limit = max(1, min(int(limit or 50), 200))
    try:
        tasks = await store.list_tasks(user["id"], limit, project)
    except Exception as e:
        log.warning("[coding] cannot load task history: %s", e)
        tasks = []

    # Desktop-dispatched tasks only live in memory; merge them without duplicates.
    seen = {t.get("task_id") for t in tasks}
    for task in hub.recent_tasks(user["id"], limit):
        if task.get("task_id") not in seen:
            tasks.append(task)
    tasks.sort(key=lambda t: t.get("started_ts") or 0, reverse=True)
    return {"tasks": tasks[:limit]}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, user: dict = Depends(get_current_user)):
    from plugins.vibecoding.backend import store

    task = await store.get_task_detail(task_id, user["id"])
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


class ContinueTaskRequest(BaseModel):
    input: str


@router.post("/tasks/{task_id}/continue")
async def continue_task(task_id: str, req: ContinueTaskRequest,
                        user: dict = Depends(get_current_user)):
    from plugins.vibecoding.backend import store
    from plugins.vibecoding.backend.server_agent import new_task_id, start_server_task

    if not req.input.strip():
        raise HTTPException(status_code=400, detail="input is required")

    row = await store.get_task(task_id, user["id"])
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")
    if row.status == "running":
        raise HTTPException(status_code=409, detail="任务仍在执行，请先等待完成或取消")
    messages = await store.get_task_messages(task_id, user["id"])
    if not messages:
        raise HTTPException(status_code=409, detail="该任务没有可复用的上下文")

    new_id = new_task_id()
    await start_server_task(
        user["id"], new_id, row.project, req.input, "continue",
        seed_messages=messages, parent_id=task_id,
    )
    return {"task_id": new_id, "parent_id": task_id, "engine": "server"}


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
