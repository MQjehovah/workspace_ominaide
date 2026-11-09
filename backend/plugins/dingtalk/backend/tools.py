"""Curated DingTalk tools exposed to Bots as plugin tools.

Raw MCP tools stay internal. Only this allowlist reaches the global catalog.
"""

from __future__ import annotations

from ai.mcp.core import MCPCallResponse, MCPContent, MCPTool
from ai.mcp.registry import tool_registry
from ai.bots import policy
from plugins.dingtalk.backend import mcp
from plugins.dingtalk.mcp_server.tools import TOOLS as MCP_TOOLS

# internal tool -> (public name, risk)
_ALLOWED = {
    "health": ("dingtalk_health", "read"),
    "search_messages": ("dingtalk_search_messages", "read"),
    "list_unread": ("dingtalk_list_unread", "read"),
    "recent_conversations": ("dingtalk_recent_conversations", "read"),
    "list_chats": ("dingtalk_list_chats", "read"),
    "list_chat_messages": ("dingtalk_list_chat_messages", "read"),
    "at_me": ("dingtalk_at_me", "read"),
    "list_chat_members": ("dingtalk_list_chat_members", "read"),
    "conversation_info": ("dingtalk_conversation_info", "read"),
    "send_message": ("dingtalk_send_message", "external"),
    "search_contacts": ("dingtalk_search_contacts", "read"),
    "get_contact": ("dingtalk_get_contact", "read"),
    "my_profile": ("dingtalk_my_profile", "read"),
    "list_events": ("dingtalk_list_events", "read"),
    "free_busy": ("dingtalk_free_busy", "read"),
    "create_event": ("dingtalk_create_event", "write"),
    "update_event": ("dingtalk_update_event", "write"),
    "cancel_event": ("dingtalk_cancel_event", "dangerous"),
    "list_todos": ("dingtalk_list_todos", "read"),
    "create_todo": ("dingtalk_create_todo", "write"),
    "update_todo": ("dingtalk_update_todo", "write"),
    "complete_todo": ("dingtalk_complete_todo", "write"),
}


def _ok(text: str) -> MCPCallResponse:
    return MCPCallResponse(content=[MCPContent(text=text)])


def _err(text: str) -> MCPCallResponse:
    return MCPCallResponse(isError=True, content=[MCPContent(text=text)])


def _handler(internal_name: str):
    async def run(user_id: int, args: dict) -> MCPCallResponse:
        try:
            data = await mcp.call(user_id, internal_name, args or {})
        except Exception as exc:
            return _err(str(exc))
        try:
            import json
            return _ok(json.dumps(data, ensure_ascii=False))
        except Exception:
            return _ok(str(data))
    return run


def register() -> None:
    for item in MCP_TOOLS:
        internal = str(item.get("name") or "")
        spec = _ALLOWED.get(internal)
        if not spec:
            continue
        public_name, risk = spec
        if tool_registry.get_handler(public_name) is not None:
            continue
        tool = MCPTool(
            name=public_name,
            description=f"[钉钉] {item.get('description') or internal}",
            inputSchema=item.get("inputSchema") or {"type": "object", "properties": {}},
            source="plugin",
            server="dingtalk",
            risk=risk,
        )
        tool_registry.register(tool, _handler(internal))
        policy.register_tool_risk(public_name, risk)
