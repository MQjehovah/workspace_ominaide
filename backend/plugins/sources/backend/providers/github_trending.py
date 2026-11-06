from __future__ import annotations

import re

from core.config.settings import settings

from .base import ProviderError, register

_SINCE_LABELS = {
    "daily": "今日",
    "weekly": "本周",
    "monthly": "本月",
}
_LANGUAGE_LABELS = {
    "any": "全部语言",
    "python": "Python",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "go": "Go",
    "rust": "Rust",
    "java": "Java",
    "c": "C",
    "cpp": "C++",
    "csharp": "C#",
    "php": "PHP",
    "ruby": "Ruby",
    "swift": "Swift",
    "kotlin": "Kotlin",
    "dart": "Dart",
}
_LANGUAGE_RE = re.compile(r"^[a-zA-Z0-9+#._-]{1,40}$")


class GithubTrendingProvider:
    key = "github_trending"
    label = "GitHub Trending"
    config_schema = {
        "type": "object",
        "properties": {
            "since": {
                "type": "string",
                "enum": ["daily", "weekly", "monthly"],
                "default": "daily",
                "description": "时间范围",
            },
            "language": {
                "type": "string",
                "default": "any",
                "description": "语言 slug，any 表示全部语言",
            },
        },
    }

    def build(self, config: dict) -> tuple[str, str]:
        config = config or {}
        since = str(config.get("since") or "daily").strip().lower()
        if since not in _SINCE_LABELS:
            raise ProviderError("GitHub Trending 的时间范围必须是 daily/weekly/monthly")

        language = str(config.get("language") or "any").strip().lower()
        if not _LANGUAGE_RE.match(language):
            raise ProviderError("GitHub Trending 的语言参数不合法")

        base = (settings.rsshub_base_url or "").strip().rstrip("/")
        if not base:
            raise ProviderError("RSSHUB_BASE_URL 未配置，无法读取 GitHub Trending")

        url = f"{base}/github/trending/{since}/{language}"
        title = (
            f"GitHub Trending · {_SINCE_LABELS[since]} · "
            f"{_LANGUAGE_LABELS.get(language, language)}"
        )
        return url, title


register(GithubTrendingProvider())
