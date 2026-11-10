"""Declarative context assembly shared by chat, coding and goal agents.

Each agent declares the sections it needs. The builder applies per-section caps,
allocates the remaining budget to conversation history, compresses history when
needed, and drops low-priority optional sections if the system context is still
too large.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai.context_window import compact_context, estimate_chars
from core.config.settings import settings


@dataclass
class ContextSection:
    key: str
    content: str
    priority: int = 50
    required: bool = False
    max_chars: int | None = None


class ContextBuilder:
    def __init__(self, *, budget_chars: int | None = None):
        self.budget_chars = int(
            budget_chars or settings.context_compress_threshold_chars or 60000
        )
        self._sections: list[ContextSection] = []
        self._history: list[dict] = []
        self._user = ""

    def section(
        self,
        key: str,
        content: str | None,
        *,
        priority: int = 50,
        required: bool = False,
        max_chars: int | None = None,
    ) -> "ContextBuilder":
        text = str(content or "").strip()
        if text:
            self._sections.append(
                ContextSection(
                    key=key,
                    content=text,
                    priority=priority,
                    required=required,
                    max_chars=max_chars,
                )
            )
        return self

    def history(self, messages: list[dict] | None) -> "ContextBuilder":
        self._history = list(messages or [])
        return self

    def user(self, content) -> "ContextBuilder":
        self._user = content
        return self

    def _trimmed_sections(self) -> list[ContextSection]:
        result = []
        for section in self._sections:
            content = section.content
            if section.max_chars and len(content) > section.max_chars:
                content = content[: section.max_chars] + "\n...[已截断]"
            result.append(
                ContextSection(
                    key=section.key,
                    content=content,
                    priority=section.priority,
                    required=section.required,
                    max_chars=section.max_chars,
                )
            )
        return result

    @staticmethod
    def _system_chars(sections: list[ContextSection]) -> int:
        return sum(len(section.content) + 32 for section in sections)

    async def build(self, *, client=None, model: str | None = None) -> list[dict]:
        sections = self._trimmed_sections()
        user_chars = len(str(self._user or ""))
        history_budget = max(
            2000,
            self.budget_chars - self._system_chars(sections) - user_chars,
        )
        history = await compact_context(
            self._history,
            client=client,
            model=model,
            threshold_chars=history_budget,
        )

        # If the system sections alone are too large, drop optional sections
        # from the lowest priority until the history budget is usable.
        while (
            sections
            and self._system_chars(sections) + user_chars + estimate_chars(history)
            > self.budget_chars
        ):
            droppable = [section for section in sections if not section.required]
            if not droppable:
                break
            victim = min(droppable, key=lambda item: item.priority)
            sections = [section for section in sections if section is not victim]

        messages = [
            {"role": "system", "content": section.content}
            for section in sorted(sections, key=lambda item: -item.priority)
        ]
        messages.extend(history)
        if self._user:
            messages.append({"role": "user", "content": self._user})
        return messages
