"""Shared AsyncOpenAI clients.

The voice path uses ASR, the agent and TTS through the same gateway. Creating
a new ``AsyncOpenAI`` per request throws away the httpx connection pool and
pays a fresh TLS handshake every time, which is very noticeable when the
gateway TLS handshake is slow.  Cache one client per (base_url, key).
"""
from __future__ import annotations

import asyncio

from openai import AsyncOpenAI

from core.logging import get_logger

log = get_logger(__name__)

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
            log.info("[clients] warmed %s", base_url)
        except Exception as e:
            log.warning("[clients] warm-up failed %s: %s", base_url, e)

    # Embedding calls sit in the voice critical path (memory lookup), so pay
    # their TLS handshake at startup too.
    try:
        from ai.llm.embeddings import generate_embedding

        await asyncio.wait_for(generate_embedding("warm"), timeout=8)
        log.info("[clients] warmed embeddings %s", settings.embedding_base_url)
    except Exception as e:
        log.warning("[clients] embedding warm-up failed: %s", e)
