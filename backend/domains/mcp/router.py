from fastapi import APIRouter, Depends
from core.auth.dependencies import get_current_user
from domains.mcp.registry import tool_registry
from domains.mcp.core import MCPCallRequest

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])


@router.get("/tools")
async def list_tools():
    """MCP: List all available tools with their schemas."""
    tools = tool_registry.get_tools()
    return {"tools": [t.model_dump() for t in tools]}


@router.post("/call")
async def call_tool(
    req: MCPCallRequest,
    user: dict = Depends(get_current_user),
):
    """MCP: Call a tool with arguments and get results."""
    result = await tool_registry.call(user["id"], req)
    return result.model_dump()
