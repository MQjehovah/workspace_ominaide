# OmniAide Phase 3 — MCP Server + 语义搜索引擎

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 MCP Server，以标准协议将系统能力暴露给外部 Agent；实现 Qdrant 语义文件搜索

**Architecture:** 系统作为 MCP Server（SSE 传输），Agent 独立运行并通过 MCP 调用系统 tools。插件可注册自定义 tools。

---

### Task 1: MCP 核心框架

**Files:**
- 创建: `backend/domains/mcp/__init__.py`
- 创建: `backend/domains/mcp/core.py` — MCPTool, MCPCallRequest/Response 定义
- 创建: `backend/domains/mcp/registry.py` — ToolRegistry (全局单例)
- 创建: `backend/domains/mcp/router.py` — SSE ListTools + CallTool
- 修改: `backend/main.py`

**Step 1: MCP Data Models (core.py)**

```python
from pydantic import BaseModel


class MCPTool(BaseModel):
    """MCP Tool definition following the protocol."""
    name: str
    description: str
    inputSchema: dict  # JSON Schema


class MCPResource(BaseModel):
    """Reference to a resource (file, etc.)"""
    uri: str
    mimeType: str | None = None
    text: str | None = None


class MCPContent(BaseModel):
    """Content block in a tool result."""
    type: str = "text"  # "text" or "resource"
    text: str | None = None
    resource: MCPResource | None = None


class MCPCallRequest(BaseModel):
    name: str
    arguments: dict = {}


class MCPCallResponse(BaseModel):
    content: list[MCPContent] = []
    isError: bool = False
```

**Step 2: Tool Registry (registry.py)**

```python
import inspect
from typing import Callable, Awaitable
from core.auth.dependencies import get_current_user
from domains.mcp.core import MCPTool, MCPCallRequest, MCPCallResponse, MCPContent

# Handler signature: (user_id: int, args: dict) -> MCPCallResponse
ToolHandler = Callable[[int, dict], Awaitable[MCPCallResponse]]


class ToolRegistry:
    """Global registry for MCP tools.
    
    Core tools are registered at startup.
    Plugins can register additional tools via register_tool().
    """
    
    def __init__(self):
        self._tools: dict[str, tuple[MCPTool, ToolHandler]] = {}

    def register(self, tool: MCPTool, handler: ToolHandler):
        self._tools[tool.name] = (tool, handler)

    def get_tools(self) -> list[MCPTool]:
        return [t for t, _ in self._tools.values()]

    def get_handler(self, name: str) -> ToolHandler | None:
        entry = self._tools.get(name)
        return entry[1] if entry else None

    async def call(self, user_id: int, req: MCPCallRequest) -> MCPCallResponse:
        handler = self.get_handler(req.name)
        if not handler:
            return MCPCallResponse(
                isError=True,
                content=[MCPContent(text=f"Tool '{req.name}' not found")]
            )
        try:
            return await handler(user_id, req.arguments)
        except Exception as e:
            return MCPCallResponse(
                isError=True,
                content=[MCPContent(text=f"Error: {str(e)}")]
            )


# Global instance
tool_registry = ToolRegistry()
```

**Step 3: Router (router.py)**

```python
from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse
from core.auth.dependencies import get_current_user
from domains.mcp.registry import tool_registry
from domains.mcp.core import MCPCallRequest

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])


@router.get("/tools")
async def list_tools():
    """MCP: List all available tools."""
    tools = tool_registry.get_tools()
    return {
        "tools": [t.model_dump() for t in tools]
    }


@router.post("/call")
async def call_tool(
    req: MCPCallRequest,
    user: dict = Depends(get_current_user),
):
    """MCP: Call a tool with arguments."""
    result = await tool_registry.call(user["id"], req)
    return result.model_dump()


@router.get("/events")
    async def stream_events(user: dict = Depends(get_current_user)):
    """MCP: SSE event stream (for future use)."""
    async def event_generator():
        yield {"event": "message", "data": "connected"}
    return EventSourceResponse(event_generator())
```

**Step 4: Register in main.py**

```python
from domains.mcp.router import router as mcp_router
app.include_router(mcp_router)
```

---

### Task 2: 核心 Tools 实现

**Files:**
- 创建: `backend/domains/mcp/tools/__init__.py`
- 创建: `backend/domains/mcp/tools/search.py` — search_files
- 创建: `backend/domains/mcp/tools/files.py` — list/get/download
- 创建: `backend/domains/mcp/tools/workspace.py` — list workspaces
- 创建: `backend/domains/mcp/tools/context.py` — get_system_context
- 创建: `backend/domains/mcp/tools/register_core.py` — 注册所有核心 tools

**Step 1: 每个 tool 是一个异步函数**

search_files tool:
```python
async def search_files(user_id: int, args: dict) -> MCPCallResponse:
    query = args.get("query", "")
    limit = args.get("limit", 10)
    # Search Qdrant for file matches
    # Fallback: search MySQL by filename
    results = await file_search_service.semantic_search(user_id, query, limit)
    return MCPCallResponse(content=[MCPContent(text=json.dumps(results, ensure_ascii=False))])
```

**Step 2: register_core.py**

在 startup 时注册所有核心 tools：

```python
from domains.mcp.registry import tool_registry
from domains.mcp.core import MCPTool

def register_core_tools():
    tool_registry.register(
        MCPTool(
            name="search_files",
            description="Semantic search for files by natural language query",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query in natural language"},
                    "limit": {"type": "integer", "description": "Max results (default 10)", "default": 10},
                    "workspace_id": {"type": "integer", "description": "Filter by workspace", "nullable": True}
                },
                "required": ["query"]
            }
        ),
        search_files
    )
    # ... more tools
```

---

### Task 3: Qdrant 语义文件搜索

**Files:**
- 创建: `backend/domains/file/embeddings.py` — Embedding 生成 + Qdrant 索引
- 创建: `backend/domains/file/search.py` — 语义搜索服务
- 修改: `backend/domains/file/service.py` — 上传确认后触发索引
- 修改: `backend/core/config/settings.py` — 添加 embedding 配置

**Step 1: Embedding Service**

使用 OpenAI Embedding API（初期云端，后续可换本地）：

```python
from openai import AsyncOpenAI
from core.config.settings import settings

client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)

async def generate_embedding(text: str) -> list[float]:
    resp = await client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return resp.data[0].embedding
```

**Step 2: Qdrant 索引**

文件上传确认后，异步提取文本 → 生成向量 → 存入 Qdrant：

```python
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance

qdrant = QdrantClient(url=settings.qdrant_url)

async def index_file(file_id: int, user_id: int, filename: str, content: str):
    vec = await generate_embedding(content[:8000])  # truncate
    qdrant.upsert(
        collection_name="file_embeddings",
        points=[PointStruct(
            id=file_id,
            vector=vec,
            payload={"user_id": user_id, "filename": filename, "file_id": file_id}
        )]
    )
```

**Step 3: 语义搜索**

```python
async def semantic_search(user_id: int, query: str, limit: int = 10) -> list[dict]:
    vec = await generate_embedding(query)
    results = qdrant.search(
        collection_name="file_embeddings",
        query_vector=vec,
        query_filter=Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]),
        limit=limit
    )
    return [{"file_id": r.payload["file_id"], "filename": r.payload["filename"], "score": r.score} for r in results]
```

---

### Task 4: 插件 Tool 注册接口

**Files:**
- 修改: `backend/core/plugin/registry.py` — 插件启动时注册 tools
- 文档: `docs/plugin-dev.md`

**Step 1: 插件 manifest 扩展**

支持 tools 声明：
```json
{
  "name": "todo",
  "tools": [
    {
      "name": "create_todo",
      "description": "Create a new todo item",
      "inputSchema": {
        "type": "object",
        "properties": {
          "title": {"type": "string"},
          "priority": {"type": "integer"}
        },
        "required": ["title"]
      }
    }
  ]
}
```

**Step 2: 插件加载时自动注册**

修改 `registry.py` 的 `_register_plugin_routes`，额外扫描插件声明的 tools 并注册到 MCP tool_registry。

---

### Task 5: 验证

```bash
# 启动后端后，验证 MCP tools 可用
curl http://localhost:8000/api/v1/mcp/tools
# 预期: 返回 tools 列表

# 测试 tool 调用
curl -X POST http://localhost:8000/api/v1/mcp/call \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name":"list_workspaces","arguments":{}}'
# 预期: 返回工作空间列表

# 前端编译
cd frontend && npx vue-tsc --noEmit
```
