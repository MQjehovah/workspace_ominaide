from typing import Callable, Awaitable
from ai.mcp.core import MCPTool, MCPCallRequest, MCPCallResponse, MCPContent

ToolHandler = Callable[[int, dict], Awaitable[MCPCallResponse | dict]]


def _to_response(result: MCPCallResponse | dict) -> MCPCallResponse:
    if isinstance(result, MCPCallResponse):
        return result
    # dict result -> wrap as text content
    if isinstance(result, dict):
        if result.get("error"):
            return MCPCallResponse(
                isError=True,
                content=[MCPContent(text=str(result.get("error")))]
            )
        import json
        try:
            text = json.dumps(result, ensure_ascii=False)
        except Exception:
            text = str(result)
        return MCPCallResponse(content=[MCPContent(text=text)])
    return MCPCallResponse(
        isError=True,
        content=[MCPContent(text=f"Unexpected result type: {type(result)}")]
    )


class ToolRegistry:
    """Global registry for MCP tools.

    Core tools are registered at startup via register_core_tools().
    Plugins can register tools during discovery.
    """

    def __init__(self):
        self._tools: dict[str, tuple[MCPTool, ToolHandler]] = {}

    def register(self, tool: MCPTool, handler: ToolHandler):
        self._tools[tool.name] = (tool, handler)

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get_tools(self, user_id: int | None = None) -> list[MCPTool]:
        tools = [t for t, _ in self._tools.values()]
        if user_id is None:
            return tools
        return [t for t in tools if getattr(t, "user_id", None) in (None, user_id)]

    def get_handler(self, name: str) -> ToolHandler | None:
        entry = self._tools.get(name)
        return entry[1] if entry else None

    async def call(self, user_id: int, req: MCPCallRequest) -> MCPCallResponse:
        entry = self._tools.get(req.name)
        if entry is None or getattr(entry[0], "user_id", None) not in (None, user_id):
            return MCPCallResponse(
                isError=True,
                content=[MCPContent(text=f"Tool '{req.name}' not found")]
            )
        handler = entry[1]
        if not handler:
            return MCPCallResponse(
                isError=True,
                content=[MCPContent(text=f"Tool '{req.name}' not found")]
            )
        try:
            result = await handler(user_id, req.arguments)
            return _to_response(result)
        except Exception as e:
            return MCPCallResponse(
                isError=True,
                content=[MCPContent(text=f"Error: {str(e)}")]
            )


tool_registry = ToolRegistry()
