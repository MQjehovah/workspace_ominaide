"""Register all core MCP tools at startup."""

from core.mcp.registry import tool_registry
from core.mcp.core import MCPTool
from core.mcp.tools.files import search_files, list_files, get_file_info, get_file_download
from core.mcp.tools.workspace_tools import list_workspaces_tool
from core.mcp.tools.context_tool import get_system_context


def register_core_tools():
    tool_registry.register(
        MCPTool(
            name="search_files",
            description="Search for files by name or keyword. Returns matching files with metadata.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (filename or keyword)"},
                    "limit": {"type": "integer", "description": "Maximum number of results", "default": 10},
                    "workspace_id": {"type": "integer", "description": "Filter by workspace ID (optional)"},
                },
                "required": ["query"],
            },
        ),
        search_files,
    )

    tool_registry.register(
        MCPTool(
            name="list_files",
            description="List files with optional filters (workspace, type, status).",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "integer", "description": "Filter by workspace ID"},
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
            name="list_workspaces",
            description="List all workspaces for the current user.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        list_workspaces_tool,
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
