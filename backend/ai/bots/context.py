"""Current bot scope for the running agent loop.

Tools (e.g. save_memory) need to know which Bot is executing without changing
the MCP handler signature. The chat endpoints / runner set this before invoking
the agent and reset it afterwards. ContextVars are copied into asyncio tasks,
so background supervisors inherit the scope as long as they are created while
the token is active.
"""
from contextvars import ContextVar, Token

_current_bot_id: ContextVar[int | None] = ContextVar("current_bot_id", default=None)
_current_run_id: ContextVar[int | None] = ContextVar("current_run_id", default=None)
_current_session_id: ContextVar[str | None] = ContextVar("current_session_id", default=None)
_current_client_kind: ContextVar[str] = ContextVar("current_client_kind", default="desktop")
_current_local_tools_enabled: ContextVar[bool] = ContextVar("current_local_tools_enabled", default=True)


def set_current_bot_id(bot_id: int | None) -> Token:
    return _current_bot_id.set(bot_id)


def reset_current_bot_id(token: Token) -> None:
    _current_bot_id.reset(token)


def get_current_bot_id() -> int | None:
    return _current_bot_id.get()


def set_current_run_id(run_id: int | None) -> Token:
    return _current_run_id.set(run_id)


def reset_current_run_id(token: Token) -> None:
    _current_run_id.reset(token)


def get_current_run_id() -> int | None:
    return _current_run_id.get()


def set_current_session_id(session_id: str | None) -> Token:
    return _current_session_id.set(session_id)


def reset_current_session_id(token: Token) -> None:
    _current_session_id.reset(token)


def get_current_session_id() -> str | None:
    return _current_session_id.get()


def set_current_client_kind(kind: str | None) -> Token:
    return _current_client_kind.set(kind or "desktop")


def reset_current_client_kind(token: Token) -> None:
    _current_client_kind.reset(token)


def get_current_client_kind() -> str:
    return _current_client_kind.get()


def set_local_tools_enabled(enabled: bool) -> Token:
    return _current_local_tools_enabled.set(bool(enabled))


def reset_local_tools_enabled(token: Token) -> None:
    _current_local_tools_enabled.reset(token)


def local_tools_enabled() -> bool:
    return _current_local_tools_enabled.get()
