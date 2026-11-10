"""Filesystem-backed template registry.

A template is a JSON file under ``SANDBOX_TEMPLATES_DIR``. Templates describe
the image, mount point, resource limits, ports and one-time setup commands.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.models import Template, TemplateSummary


class TemplateError(ValueError):
    pass


class TemplateRegistry:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self._templates: dict[str, Template] = {}

    def load(self) -> dict[str, Template]:
        templates: dict[str, Template] = {}
        if not self.directory.exists():
            self._templates = templates
            return templates
        for path in sorted(self.directory.glob("*.json")):
            if path.name.startswith("."):
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise TemplateError(f"cannot load template {path.name}: {exc}") from exc
            payload.setdefault("id", path.stem)
            try:
                template = Template.model_validate(payload)
            except Exception as exc:
                raise TemplateError(f"invalid template {path.name}: {exc}") from exc
            if template.id in templates:
                raise TemplateError(f"duplicate template id: {template.id}")
            if not template.workdir.startswith("/"):
                raise TemplateError(f"template {template.id}: workdir must be absolute")
            if not template.image:
                raise TemplateError(f"template {template.id}: image is required")
            templates[template.id] = template
        self._templates = templates
        return templates

    def get(self, template_id: str) -> Template:
        template = self._templates.get(template_id)
        if template is None:
            raise TemplateError(f"template not found: {template_id}")
        return template

    def list(self) -> list[TemplateSummary]:
        return [
            TemplateSummary(
                id=t.id,
                name=t.name,
                description=t.description,
                image=t.image,
                workdir=t.workdir,
                ports=t.ports,
                setup_count=len(t.setup),
            )
            for t in sorted(self._templates.values(), key=lambda item: item.id)
        ]


registry = TemplateRegistry("/app/templates")
