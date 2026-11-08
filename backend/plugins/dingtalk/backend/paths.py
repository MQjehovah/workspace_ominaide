"""Per-user DingTalk workspace and DWS environment."""

from __future__ import annotations

import os
from pathlib import Path

from core.paths import user_root


def dingtalk_root(user_id: int) -> Path:
    return user_root(user_id) / "dingtalk"


def ensure_dingtalk_workspace(user_id: int) -> Path:
    base = dingtalk_root(user_id)
    for relative in (".dws", "home", "logs"):
        try:
            (base / relative).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    for relative in ("", ".dws", "home", "logs"):
        try:
            os.chmod(base / relative, 0o700)
        except OSError:
            pass
    return base


def dingtalk_env(user_id: int) -> dict[str, str]:
    ensure_dingtalk_workspace(user_id)
    base = dingtalk_root(user_id)
    return {
        "DWS_CONFIG_DIR": str(base / ".dws"),
        "HOME": str(base / "home"),
    }
