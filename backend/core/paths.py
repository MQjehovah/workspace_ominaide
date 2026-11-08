"""Per-user runtime paths.

Every user owns one directory tree:

    <workspace_root>/<user_id>/
        projects/            coding projects
        tmp/

Production mounts the host data volume at ``/data`` so the host path is
``/data/docker/omniaide/data/workspace/<user_id>``.
"""

from __future__ import annotations

import os
from pathlib import Path

from core.config.settings import settings


def workspace_root() -> Path:
    return Path(settings.workspace_root or "/data/workspace").expanduser()


def user_root(user_id: int) -> Path:
    return workspace_root() / str(int(user_id))


def projects_root(user_id: int) -> Path:
    """Directory that contains a user's coding projects.

    ``coding_workspace_root`` is a legacy/test override that applies directly.
    Production leaves it empty so each user gets their own subdirectory.
    """
    override = (settings.coding_workspace_root or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return user_root(user_id) / "projects"


def ensure_user_workspace(user_id: int) -> Path:
    """Create the user's directory tree; safe to call repeatedly."""
    root = user_root(user_id)
    for relative in ("projects", "tmp"):
        try:
            (root / relative).mkdir(parents=True, exist_ok=True)
        except OSError:
            # Read-only/test environments: path validation still works, only
            # directory creation is skipped.
            pass
    return root


def is_within(root: Path, path: Path) -> bool:
    """True when ``path`` is ``root`` or inside it (both already resolved)."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
