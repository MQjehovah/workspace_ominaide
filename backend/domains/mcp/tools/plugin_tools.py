"""Utilities for plugins to register MCP tools."""

from collections.abc import Callable
from domains.mcp.registry import tool_registry
from domains.mcp.core import MCPTool

_plugin_handlers: dict[str, Callable] = {}


def register_plugin_tool_handler(tool_name: str, handler: Callable):
    _plugin_handlers[tool_name] = handler


def get_plugin_handler(tool_name: str) -> Callable | None:
    return _plugin_handlers.get(tool_name)


def register_plugin_tools_from_manifest(manifest: dict, plugin_name: str):
    tools = manifest.get("tools", [])
    for tool_def in tools:
        name = tool_def["name"]
        handler = _plugin_handlers.get(name)
        if handler:
            tool_registry.register(
                MCPTool(
                    name=name,
                    description=tool_def.get("description", ""),
                    inputSchema=tool_def.get("inputSchema", {"type": "object", "properties": {}}),
                ),
                lambda user_id, args, _handler=handler: _handler(user_id, args),
            )
