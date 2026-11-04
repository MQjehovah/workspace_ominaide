"""Register all core MCP tools at startup."""

from core.ai.mcp.registry import tool_registry
from core.ai.mcp.core import MCPTool
from core.ai.mcp.tools.files import search_files, list_files, get_file_info, get_file_download
from core.ai.mcp.tools.context_tool import get_system_context
from core.ai.mcp.tools.knowledge import TOOLS as KNOWLEDGE_TOOLS
from core.ai.mcp.tools.personal import TOOLS as PERSONAL_TOOLS
from core.ai.mcp.tools.productivity import TOOLS as PRODUCTIVITY_TOOLS
from core.ai.mcp.tools.documents import TOOLS as DOCUMENT_TOOLS
from core.ai.mcp.tools.coding import TOOLS as CODING_TOOLS
from core.ai.mcp.tools.web import TOOLS as WEB_TOOLS
from core.ai.mcp.tools.management import TOOLS as MANAGEMENT_TOOLS


def register_core_tools():
    for tool, handler in KNOWLEDGE_TOOLS:
        tool_registry.register(tool, handler)
    for tool, handler in PERSONAL_TOOLS:
        tool_registry.register(tool, handler)
    for tool, handler in PRODUCTIVITY_TOOLS:
        tool_registry.register(tool, handler)
    for tool, handler in DOCUMENT_TOOLS:
        tool_registry.register(tool, handler)
    for tool, handler in CODING_TOOLS:
        tool_registry.register(tool, handler)
    for tool, handler in WEB_TOOLS:
        tool_registry.register(tool, handler)
    for tool, handler in MANAGEMENT_TOOLS:
        tool_registry.register(tool, handler)
    tool_registry.register(
        MCPTool(
            name="search_files",
            description="Search for files by name or keyword. Returns matching files with metadata.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (filename or keyword)"},
                    "limit": {"type": "integer", "description": "Maximum number of results", "default": 10},
                },
                "required": ["query"],
            },
        ),
        search_files,
    )

    tool_registry.register(
        MCPTool(
            name="list_files",
            description="List files with optional filters (type, status).",
            inputSchema={
                "type": "object",
                "properties": {
                    "mime_type": {"type": "string", "description": "Filter by MIME type prefix (e.g. 'image/', 'application/pdf')"},
                    "status": {"type": "string", "description": "File status: active or trash", "default": "active"},
                    "limit": {"type": "integer", "description": "Max results", "default": 50},
                    "page": {"type": "integer", "description": "Page number", "default": 1},
                },
            },
        ),
        list_files,
    )

    tool_registry.register(
        MCPTool(
            name="get_file",
            description="Get detailed information about a specific file by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_id": {"type": "integer", "description": "File ID"},
                },
                "required": ["file_id"],
            },
        ),
        get_file_info,
    )

    tool_registry.register(
        MCPTool(
            name="get_file_download_url",
            description="Get a temporary download URL for a file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_id": {"type": "integer", "description": "File ID"},
                },
                "required": ["file_id"],
            },
        ),
        get_file_download,
    )

    tool_registry.register(
        MCPTool(
            name="get_system_context",
            description="Get current system context: user stats, available capabilities, and timestamp.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        get_system_context,
    )
