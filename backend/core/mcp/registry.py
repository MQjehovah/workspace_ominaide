from typing import Callable, Awaitable
from core.mcp.core import MCPTool, MCPCallRequest, MCPCallResponse, MCPContent

ToolHandler = Callable[[int, dict], Awaitable[MCPCallResponse]]


class ToolRegistry:
    """Global registry for MCP tools.

    Core tools are registered at startup via register_core_tools().
    Plugins can register tools during discovery.
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


tool_registry = ToolRegistry()
