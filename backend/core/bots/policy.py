"""Tool risk classification and approval policy for bot runs.

Policy resolution order:
1. Bot's ``risk_policy["tools"][name]`` (explicit per-tool override)
2. Bot's ``risk_policy[risk_level]`` (level override)
3. Built-in default: read/write = auto, exec/external = ask
"""
from core.bots.models import Bot

RISK_READ = "read"
RISK_WRITE = "write"
RISK_EXEC = "exec"
RISK_EXTERNAL = "external"

DEFAULT_LEVEL_POLICY = {
    RISK_READ: "auto",
    RISK_WRITE: "auto",
    RISK_EXEC: "ask",
    RISK_EXTERNAL: "ask",
}

# Explicit classifications for tools shipped with the backend.
TOOL_RISK = {
    "search_files": RISK_READ,
    "list_files": RISK_READ,
    "get_file": RISK_READ,
    "get_file_download_url": RISK_READ,
    "get_system_context": RISK_READ,
    "search_knowledge": RISK_READ,
    "unified_search": RISK_READ,
    "list_schedule_events": RISK_READ,
    "list_recent_emails": RISK_READ,
    "get_current_time": RISK_READ,
    "save_memory": RISK_WRITE,
    "create_schedule_event": RISK_WRITE,
    "update_schedule_event": RISK_WRITE,
    "delete_schedule_event": RISK_WRITE,
    "create_note": RISK_WRITE,
    "update_note": RISK_WRITE,
    "delete_note": RISK_WRITE,
    "create_todo": RISK_WRITE,
    "update_todo": RISK_WRITE,
    "complete_todo": RISK_WRITE,
    "send_email": RISK_EXTERNAL,
    "send_mail": RISK_EXTERNAL,
    "send_notification": RISK_WRITE,
    "create_word_document": RISK_WRITE,
    "create_presentation": RISK_WRITE,
    "list_coding_projects": RISK_READ,
    "list_coding_runs": RISK_READ,
    "get_coding_run": RISK_READ,
    "web_search": RISK_READ,
    "fetch_url": RISK_READ,
    "delegate_coding": RISK_WRITE,
}

_EXEC_PREFIXES = ("exec", "shell", "command", "script", "terminal", "quicklink", "vibecoding", "run_")
_EXTERNAL_PREFIXES = ("send_email", "send_mail", "mail.send", "purchase", "pay_", "payment", "device.control", "webhook", "post_")
_WRITE_PREFIXES = (
    "create_", "update_", "delete_", "save_", "add_", "set_", "remove_",
    "clear_", "toggle_", "complete_", "archive_", "move_", "upload_",
)


def classify_tool(name: str) -> str:
    name = (name or "").strip().lower()
    if name in TOOL_RISK:
        return TOOL_RISK[name]
    if name.startswith(_EXEC_PREFIXES):
        return RISK_EXEC
    if name.startswith(_EXTERNAL_PREFIXES):
        return RISK_EXTERNAL
    if name.startswith(_WRITE_PREFIXES):
        return RISK_WRITE
    return RISK_READ


def resolve_risk(bot: Bot | None, name: str) -> str:
    custom = (getattr(bot, "risk_policy", None) or {}) if bot is not None else {}
    tools = custom.get("tools") or {}
    spec = tools.get(name)
    if isinstance(spec, str) and spec in DEFAULT_LEVEL_POLICY:
        return spec
    if isinstance(spec, dict) and spec.get("risk") in DEFAULT_LEVEL_POLICY:
        return spec["risk"]
    return classify_tool(name)


def decide(bot: Bot | None, name: str) -> tuple[str, str]:
    """Return ``(risk_level, decision)`` where decision is auto/ask/deny."""
    risk = resolve_risk(bot, name)
    custom = (getattr(bot, "risk_policy", None) or {}) if bot is not None else {}

    tools = custom.get("tools") or {}
    spec = tools.get(name)
    if isinstance(spec, str) and spec in ("auto", "ask", "deny"):
        return risk, spec
    if isinstance(spec, dict) and spec.get("decision") in ("auto", "ask", "deny"):
        return risk, spec["decision"]

    decision = custom.get(risk) or DEFAULT_LEVEL_POLICY.get(risk, "ask")
    if decision not in ("auto", "ask", "deny"):
        decision = DEFAULT_LEVEL_POLICY.get(risk, "ask")
    return risk, decision
