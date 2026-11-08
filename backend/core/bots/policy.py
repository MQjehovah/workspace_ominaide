"""Tool risk classification and approval policy for bot runs.

Policy resolution order:
1. Bot's ``risk_policy["tools"][name]`` (explicit per-tool override)
2. Bot's ``risk_policy[risk_level]`` (level override)
3. Built-in default: read/write = auto, exec/external = ask
"""
import os
import re
import shlex

from core.bots.models import Bot

RISK_READ = "read"
RISK_WRITE = "write"
RISK_EXEC = "exec"
RISK_EXTERNAL = "external"
RISK_DANGEROUS = "dangerous"

DEFAULT_LEVEL_POLICY = {
    RISK_READ: "auto",
    RISK_WRITE: "auto",
    RISK_EXEC: "ask",
    RISK_EXTERNAL: "ask",
    RISK_DANGEROUS: "ask",
}

# Explicit classifications for tools shipped with the backend.
TOOL_RISK = {
    "search_files": RISK_READ,
    "list_files": RISK_READ,
    "get_file": RISK_READ,
    "get_file_download_url": RISK_READ,
    "get_system_context": RISK_READ,
    "list_recent_chats": RISK_READ,
    "search_business_objects": RISK_READ,
    "get_business_object": RISK_READ,
    "list_business_comments": RISK_READ,
    "comment_business_object": RISK_WRITE,
    "update_business_comment": RISK_WRITE,
    "delete_business_comment": RISK_DANGEROUS,
    "search_knowledge": RISK_READ,
    "unified_search": RISK_READ,
    "list_schedule_events": RISK_READ,
    "find_schedule_events": RISK_READ,
    "get_schedule_event": RISK_READ,
    "cancel_schedule_event": RISK_DANGEROUS,
    "list_recent_emails": RISK_READ,
    "get_current_time": RISK_READ,
    "save_memory": RISK_WRITE,
    "propose_memory": RISK_WRITE,
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
    "dws_cli": RISK_WRITE,
    "create_word_document": RISK_WRITE,
    "create_presentation": RISK_WRITE,
    "list_coding_projects": RISK_READ,
    "list_coding_runs": RISK_READ,
    "get_coding_run": RISK_READ,
    "web_search": RISK_READ,
    "fetch_url": RISK_READ,
    "run_shell": RISK_EXEC,
    "local_shell": RISK_EXEC,
    "local_mcp_search": RISK_READ,
    "local_mcp_call": RISK_EXEC,
    "local_shell_start": RISK_EXEC,
    "local_shell_wait": RISK_READ,
    "local_shell_cancel": RISK_EXEC,
    "local_list_dir": RISK_READ,
    "local_read_file": RISK_READ,
    "local_write_file": RISK_WRITE,
    "local_grep": RISK_READ,
    "list_local_machines": RISK_READ,
    "google_gmail_search": RISK_READ,
    "google_gmail_read": RISK_READ,
    "google_gmail_send": RISK_EXTERNAL,
    "google_calendar_list": RISK_READ,
    "google_calendar_create": RISK_WRITE,
    "google_drive_search": RISK_READ,
    "google_drive_read": RISK_READ,
    "google_drive_upload": RISK_WRITE,
    "delegate_coding": RISK_WRITE,
    # External side effects: require explicit approval in chat.
    "ha_toggle": RISK_EXTERNAL,
    "ha_call_service": RISK_EXTERNAL,
    "send_email": RISK_EXTERNAL,
    "device_music_control": RISK_EXTERNAL,
    "play_device_music": RISK_EXTERNAL,
    # Destructive operations: require explicit approval in chat.
    "todo_delete": RISK_DANGEROUS,
    "event_delete": RISK_DANGEROUS,
    "note_delete": RISK_DANGEROUS,
    "file_delete": RISK_DANGEROUS,
    "project_delete": RISK_DANGEROUS,
    "routine_delete": RISK_DANGEROUS,
    "sources_delete": RISK_DANGEROUS,
    "memory_delete": RISK_DANGEROUS,
}

_EXEC_PREFIXES = ("exec", "shell", "command", "script", "terminal", "quicklink", "vibecoding", "run_")
_EXTERNAL_PREFIXES = ("send_email", "send_mail", "mail.send", "purchase", "pay_", "payment", "device.control", "webhook", "post_")
_WRITE_PREFIXES = (
    "create_", "update_", "delete_", "save_", "add_", "set_", "remove_",
    "clear_", "toggle_", "complete_", "archive_", "move_", "upload_",
)


_DYNAMIC_RISK: dict[str, str] = {}


def register_tool_risk(name: str, risk: str) -> None:
    """Let the MCP hub declare risk for dynamically discovered tools."""
    if risk in DEFAULT_LEVEL_POLICY:
        _DYNAMIC_RISK[name] = risk


def unregister_tool_risk(name: str) -> None:
    _DYNAMIC_RISK.pop(name, None)


def classify_tool(name: str) -> str:
    name = (name or "").strip().lower()
    if name in _DYNAMIC_RISK:
        return _DYNAMIC_RISK[name]
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


_SAFE_SHELL_COMMANDS = {
    "ls", "pwd", "whoami", "id", "hostname", "uname", "date", "uptime",
    "df", "du", "free", "ps", "cat", "head", "tail", "wc", "grep", "rg",
    "find", "echo", "which", "git",
}
_SHELL_META = (";", "&&", "||", "|", ">", "<", "`", "$(", "\n")
_SHELL_SECRET_HINTS = (".env", ".ssh", "id_rsa", "id_ed25519", "/etc/shadow")


def shell_decision(command: str, default: str = "ask") -> str:
    """Return auto only for simple read-only commands; ask for everything else.

    This is UX, not a security boundary: shell syntax can always be obfuscated.
    """
    command = (command or "").strip()
    if not command or any(meta in command for meta in _SHELL_META):
        return default
    lower = command.lower()
    if any(hint in lower for hint in _SHELL_SECRET_HINTS):
        return default
    try:
        tokens = shlex.split(command)
    except ValueError:
        return default
    if not tokens:
        return default
    base = os.path.basename(tokens[0])
    if base not in _SAFE_SHELL_COMMANDS:
        return default
    if base == "find" and any(t in ("-delete", "-exec", "-execdir") for t in tokens):
        return default
    if base == "git":
        if len(tokens) < 2 or tokens[1] not in ("status", "log", "diff", "show", "branch", "remote"):
            return default
    return "auto"


def decide(bot: Bot | None, name: str, arguments: dict | None = None) -> tuple[str, str]:
    """Return ``(risk_level, decision)`` where decision is auto/ask/deny."""
    risk = resolve_risk(bot, name)
    custom = (getattr(bot, "risk_policy", None) or {}) if bot is not None else {}

    tools = custom.get("tools") or {}
    spec = tools.get(name)
    if isinstance(spec, str) and spec in ("auto", "ask", "deny"):
        return risk, spec
    if isinstance(spec, dict) and spec.get("decision") in ("auto", "ask", "deny"):
        return risk, spec["decision"]
    if isinstance(spec, dict) and spec.get("decision") == "smart":
        return risk, shell_decision((arguments or {}).get("command", ""))

    if name == "run_shell":
        return risk, shell_decision((arguments or {}).get("command", ""))

    if name.startswith("local_") or name == "list_local_machines":
        # local_mcp_call is a generic gateway to arbitrary local MCP tools, so
        # it asks by default. Other local tools are gated by the desktop policy.
        default = "ask" if name == "local_mcp_call" else "auto"
        decision = custom.get(risk) or default
        if decision not in ("auto", "ask", "deny"):
            decision = default
        return risk, decision

    decision = custom.get(risk) or DEFAULT_LEVEL_POLICY.get(risk, "ask")
    if decision not in ("auto", "ask", "deny"):
        decision = DEFAULT_LEVEL_POLICY.get(risk, "ask")
    return risk, decision
