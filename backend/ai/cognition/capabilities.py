"""Capability descriptors built from the unified tool registry."""

from __future__ import annotations

from dataclasses import dataclass, field

from ai.bots import policy
from ai.mcp.registry import tool_registry


@dataclass
class Capability:
    key: str
    title: str
    description: str = ""
    source: str = "builtin"
    risk: str = "read"
    reversible: bool = True
    cost: str = "low"
    data_scopes: list[str] = field(default_factory=list)


def normalize_capability_key(name: str, arguments: dict | None = None) -> str:
    """Resolve a gateway wrapper to the actual capability key."""
    if name == "tool_call":
        raw, _ = policy._tool_call_target(arguments)
        key = raw or name
    else:
        key = name
    if key.startswith("local:"):
        return key
    for prefix in ("builtin:", "plugin:", "mcp:", "skill:"):
        if key.startswith(prefix):
            return key[len(prefix):]
    return key


def _describe_tool(tool, bot=None) -> Capability:
    risk = tool.risk or policy.resolve_risk(bot, tool.name)
    return Capability(
        key=tool.name,
        title=tool.name,
        description=tool.description or "",
        source=tool.source or "builtin",
        risk=risk,
        reversible=risk in ("read", "suggest"),
        cost="low",
        data_scopes=[],
    )


def describe_capability(key: str, bot=None) -> Capability:
    tools = {tool.name: tool for tool in tool_registry.get_tools()}
    tool = tools.get(key)
    if tool is not None:
        return _describe_tool(tool, bot)
    risk = policy.classify_tool(key)
    source = "local" if key.startswith("local:") else "unknown"
    return Capability(
        key=key,
        title=key,
        description="",
        source=source,
        risk=risk,
        reversible=risk in ("read", "suggest"),
    )


def list_capabilities(user_id: int, bot=None) -> list[Capability]:
    return [_describe_tool(tool, bot) for tool in tool_registry.get_tools(user_id=user_id)]


def capability_dict(cap: Capability) -> dict:
    return {
        "key": cap.key,
        "title": cap.title,
        "description": cap.description,
        "source": cap.source,
        "risk": cap.risk,
        "reversible": cap.reversible,
        "cost": cap.cost,
        "data_scopes": cap.data_scopes,
    }
