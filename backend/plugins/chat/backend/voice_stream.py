"""Sentence-pipelined voice streaming helpers.

The device uploads one recorded utterance (ASR is still one-shot), then this
module converts the agent's token stream into a low-latency audio stream:

  agent tokens -> sentence queue -> TTS (PCM) -> audio frames

Text deltas, status updates and base64 PCM frames are emitted as NDJSON so the
firmware can parse them line-by-line while playing audio.
"""
from __future__ import annotations

import json
from typing import AsyncIterator

from openai import AsyncOpenAI

from core.config.settings import settings

_SENT_END = set("。！？!?；;\n")
_MAX_SENT = 90


async def read_audio(resp) -> bytes:
    data = getattr(resp, "content", None)
    if data is None:
        data = await resp.aread() if hasattr(resp, "aread") else resp.read()
    return data or b""


def parse_wav(data: bytes) -> tuple[int, int, int]:
    """Return (sample_rate, data_offset, data_length) for a RIFF/WAVE buffer."""
    if len(data) < 44 or not data.startswith(b"RIFF"):
        raise ValueError("not a WAV file")
    rate = int.from_bytes(data[24:28], "little")
    i = 12
    while i + 8 <= len(data):
        chunk = data[i:i + 4]
        size = int.from_bytes(data[i + 4:i + 8], "little")
        if chunk == b"data":
            off = i + 8
            return rate, off, min(size, len(data) - off)
        i += 8 + size + (size & 1)
    raise ValueError("WAV data chunk not found")


async def tts_pcm(
    text: str,
    client: AsyncOpenAI,
    voice: str | None = None,
) -> tuple[bytes, int]:
    """Synthesize one sentence, preferring raw PCM (24kHz mono 16-bit)."""
    model = settings.tts_model
    voice = voice or settings.tts_voice
    try:
        speech = await client.audio.speech.create(
            model=model, input=text, voice=voice, response_format="pcm",
        )
        data = await read_audio(speech)
        if data:
            return data, 24000
    except Exception:
        pass

    speech = await client.audio.speech.create(
        model=model, input=text, voice=voice, response_format="wav",
    )
    data = await read_audio(speech)
    rate, off, length = parse_wav(data)
    return data[off:off + length], rate


def take_sentences(buf: str, *, flush: bool = False) -> tuple[list[str], str]:
    """Split a growing token buffer into speakable sentences."""
    out: list[str] = []
    start = 0
    for i, ch in enumerate(buf):
        if ch in _SENT_END:
            piece = buf[start:i + 1].strip()
            if piece:
                out.append(piece)
            start = i + 1
    rest = buf[start:]
    while len(rest) > _MAX_SENT:
        out.append(rest[:_MAX_SENT].strip())
        rest = rest[_MAX_SENT:]
    if flush and rest.strip():
        out.append(rest.strip())
        rest = ""
    return out, rest


async def iter_agent_events(stream) -> AsyncIterator[dict]:
    """Make run_agent_stream's SSE strings consumable as dicts."""
    async for raw in stream:
        if not raw:
            continue
        line = raw.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload:
            continue
        try:
            ev = json.loads(payload)
        except Exception:
            continue
        if isinstance(ev, dict):
            yield ev
