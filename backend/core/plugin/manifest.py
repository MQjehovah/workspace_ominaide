"""Unified plugin manifest loading and validation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    version: str = "0.0.0"
    title: str = ""
    description: str = ""
    icon: str = ""
    permissions: list[str] = Field(default_factory=list)
    routes: dict[str, str] = Field(default_factory=dict)
    tools: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        value = (value or "").strip()
        if not _ID_RE.match(value):
            raise ValueError("manifest id must match [a-z0-9][a-z0-9_-]*")
        return value


def _from_legacy_package(pkg: dict) -> dict:
    ns = pkg.get("omniaide") or pkg.get("mqbox") or {}
    return {
        "id": ns.get("id") or pkg.get("name"),
        "version": pkg.get("version", "0.0.0"),
        "title": ns.get("displayName") or pkg.get("displayName") or pkg.get("name"),
        "description": pkg.get("description", ""),
        "icon": ns.get("icon", ""),
        "permissions": ns.get("permissions", []),
        "routes": ns.get("routes", {}),
        "tools": ns.get("tools", []),
        "main": pkg.get("main", "dist/index.js"),
        "builtin": False,
    }


def load_manifest(
    plugin_dir: Path,
    *,
    expected_id: str | None = None,
) -> dict:
    """Load and normalize either manifest.json or legacy package.json.

    ``expected_id`` enforces that the manifest id matches the directory name.
    Raises ``ValueError`` for missing/invalid manifests.
    """
    manifest_path = plugin_dir / "manifest.json"
    pkg_path = plugin_dir / "package.json"

    if manifest_path.exists():
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    elif pkg_path.exists():
        raw = _from_legacy_package(json.loads(pkg_path.read_text(encoding="utf-8")))
    else:
        raise ValueError(f"missing manifest.json/package.json: {plugin_dir}")

    data = dict(raw)
    data["id"] = data.get("id") or data.get("name") or plugin_dir.name
    data["title"] = data.get("title") or data.get("displayName") or data["id"]
    try:
        manifest = PluginManifest.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"invalid manifest {plugin_dir}: {exc}") from exc

    if expected_id is not None and manifest.id != expected_id:
        raise ValueError(
            f"manifest id '{manifest.id}' does not match directory '{expected_id}'"
        )
    return manifest.model_dump()


def find_plugin_source(root: Path) -> tuple[Path, dict]:
    """Find the directory containing manifest.json/package.json inside a zip."""
    manifests = list(root.rglob("manifest.json"))
    if manifests:
        source = manifests[0].parent
    else:
        packages = list(root.rglob("package.json"))
        if not packages:
            raise ValueError("No manifest.json or package.json found in plugin archive")
        source = packages[0].parent
    return source, load_manifest(source)
