from __future__ import annotations

from .base import ProviderError, register


class RssProvider:
    key = "rss"
    label = "RSS / Atom"
    config_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "RSS / Atom 订阅地址",
            },
        },
        "required": ["url"],
    }

    def build(self, config: dict) -> tuple[str, str]:
        url = str((config or {}).get("url") or "").strip()
        if not url:
            raise ProviderError("RSS 地址不能为空")
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ProviderError("RSS 地址必须以 http:// 或 https:// 开头")
        title = str((config or {}).get("title") or "RSS").strip() or "RSS"
        return url, title


register(RssProvider())
