"""Discover and parse Agent Skills (SKILL.md) from the filesystem."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from core.config.settings import settings

_SKILL_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_BUILTIN_DIR = Path(__file__).resolve().parents[2] / "skills" / "builtin"


@dataclass
class SkillDefinition:
    key: str
    name: str
    description: str
    body: str
    path: Path
    scope: str = "builtin"
    owner_id: int | None = None
    allowed_tools: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def summary(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "scope": self.scope,
            "allowed_tools": self.allowed_tools,
            "metadata": self.metadata,
        }


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except Exception:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, parts[2].lstrip("\n")


def _load_skill(directory: Path, scope: str, owner_id: int | None = None) -> SkillDefinition | None:
    skill_file = directory / "SKILL.md"
    if not skill_file.is_file():
        return None
    try:
        text = skill_file.read_text(encoding="utf-8")
    except Exception:
        return None
    meta, body = _parse_frontmatter(text)
    key = str(meta.get("name") or directory.name).strip()
    if not _SKILL_RE.match(key):
        return None
    description = str(meta.get("description") or "").strip()
    if not description:
        return None
    name = str(meta.get("name") or key).strip()
    allowed = meta.get("allowed-tools") or []
    if isinstance(allowed, str):
        allowed = [allowed]
    allowed_tools = [str(x).strip() for x in allowed if str(x).strip()]
    metadata = meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {}
    return SkillDefinition(
        key=key,
        name=name,
        description=description,
        body=body.strip(),
        path=directory,
        scope=scope,
        owner_id=owner_id,
        allowed_tools=allowed_tools,
        metadata=metadata,
    )


def _iter_scope(root: Path, scope: str) -> list[SkillDefinition]:
    if not root.is_dir():
        return []
    out: list[SkillDefinition] = []
    for child in sorted(root.iterdir()):
        if child.is_dir():
            skill = _load_skill(child, scope)
            if skill:
                out.append(skill)
    return out


def discover_skills() -> dict[str, SkillDefinition]:
    skills: dict[str, SkillDefinition] = {}
    for skill in _iter_scope(_BUILTIN_DIR, "builtin"):
        skills[skill.key] = skill

    root = Path(settings.skills_dir)
    if not root.is_absolute():
        root = Path.cwd() / root
    for scope, base in (("user", root / "users"), ("bot", root / "bots")):
        if not base.is_dir():
            continue
        for owner_dir in sorted(base.iterdir()):
            if not owner_dir.is_dir():
                continue
            try:
                owner_id = int(owner_dir.name)
            except ValueError:
                owner_id = None
            for skill in _iter_scope(owner_dir, scope):
                skill.owner_id = owner_id
                skills[skill.key] = skill
    return skills


def get_skill(key: str) -> SkillDefinition | None:
    return discover_skills().get(key)


def list_skills() -> list[SkillDefinition]:
    return sorted(discover_skills().values(), key=lambda s: s.key)
