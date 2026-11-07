"""Shared AsyncOpenAI clients.

The voice path uses ASR, the agent and TTS through the same gateway. Creating
a new ``AsyncOpenAI`` per request throws away the httpx connection pool and
pays a fresh TLS handshake every time, which is very noticeable when the
gateway TLS handshake is slow.  Cache one client per (base_url, key).
"""
from __future__ import annotations

import asyncio

from openai import AsyncOpenAI

_clients: dict[tuple[str, str], AsyncOpenAI] = {}


def get_openai_client(base_url: str, api_key: str) -> AsyncOpenAI:
    key = (base_url or "", api_key or "")
    client = _clients.get(key)
    if client is None:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        _clients[key] = client
    return client


async def warm_voice_clients() -> None:
    """Warm the gateway TLS/HTTP pool after startup.

    The first request after a container restart otherwise pays the full TLS
    handshake inside the user's first voice query.
    """
    from core.config.settings import settings

    targets = {
        (settings.llm_base_url, settings.llm_api_key or ""),
        (settings.asr_base_url, settings.asr_api_key or settings.llm_api_key or ""),
        (settings.tts_base_url, settings.tts_api_key or settings.llm_api_key or ""),
    }
    for base_url, api_key in targets:
        if not base_url or not api_key:
            continue
        try:
            client = get_openai_client(base_url, api_key)
            await asyncio.wait_for(client.models.list(), timeout=8)
            print(f"[clients] warmed {base_url}", flush=True)
        except Exception as e:
            print(f"[clients] warm-up failed {base_url}: {e}", flush=True)
