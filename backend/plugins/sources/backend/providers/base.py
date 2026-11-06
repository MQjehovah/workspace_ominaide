"""Provider registry for information sources."""

from __future__ import annotations

from typing import Protocol


class ProviderError(ValueError):
    """A source configuration cannot be turned into a fetchable URL."""


class SourceProvider(Protocol):
    key: str
    label: str
    config_schema: dict

    def build(self, config: dict) -> tuple[str, str]:
        """Return (fetch_url, display_title)."""


_PROVIDERS: dict[str, SourceProvider] = {}


def register(provider: SourceProvider) -> None:
    _PROVIDERS[provider.key] = provider


def get_provider(key: str) -> SourceProvider:
    provider = _PROVIDERS.get(key)
    if provider is None:
        raise ProviderError(f"未知资讯源类型: {key}")
    return provider


def list_providers() -> list[dict]:
    return [
        {
            "key": provider.key,
            "label": provider.label,
            "config_schema": provider.config_schema,
        }
        for provider in _PROVIDERS.values()
    ]
