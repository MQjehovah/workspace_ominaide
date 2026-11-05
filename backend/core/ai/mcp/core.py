from pydantic import BaseModel


class MCPTool(BaseModel):
    """MCP Tool definition following the protocol."""
    name: str
    description: str
    inputSchema: dict  # JSON Schema
    # Metadata for the unified catalog. Built-in tools keep these defaults.
    source: str = "builtin"
    server: str | None = None
    risk: str | None = None
    user_id: int | None = None


class MCPResource(BaseModel):
    """Reference to a resource (file, etc.)"""
    uri: str
    mimeType: str | None = None
    text: str | None = None


class MCPContent(BaseModel):
    """Content block in a tool result."""
    type: str = "text"
    text: str | None = None
    resource: MCPResource | None = None


class MCPCallRequest(BaseModel):
    name: str
    arguments: dict = {}


class MCPCallResponse(BaseModel):
    content: list[MCPContent] = []
    isError: bool = False
