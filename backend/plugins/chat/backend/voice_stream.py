"""Sentence-pipelined voice streaming helpers.

The device uploads one recorded utterance (ASR is still one-shot), then this
module converts the agent's token stream into a low-latency audio stream:

  agent tokens -> sentence queue -> TTS (PCM) -> audio frames

Text deltas, status updates and base64 PCM frames are emitted as NDJSON so the
firmware can parse them line-by-line while playing audio.
"""
from __future__ import annotations

import json
import time
from typing import AsyncIterator

from openai import AsyncOpenAI

from core.config.settings import settings

_SENT_END = set("。！？!?；;\n")
_SOFT_END = set("，,、：:")
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
    if settings.tts_send_format:
        try:
            speech = await client.audio.speech.create(
                model=model, input=text, voice=voice, response_format="pcm",
            )
            data = await read_audio(speech)
            if data:
                return data, 24000
        except Exception:
            pass

    kwargs = {"model": model, "input": text, "voice": voice}
    if settings.tts_send_format:
        kwargs["response_format"] = "wav"
    speech = await client.audio.speech.create(**kwargs)
    data = await read_audio(speech)
    rate, off, length = parse_wav(data)
    return data[off:off + length], rate


# Circuit breaker: Microsoft's edge endpoint starts timing out after a few
# bursts from the same IP, so skip it for a while after a failure instead of
# making every request wait for a 20s socket timeout.
_edge_blocked_until = 0.0


def edge_ready() -> bool:
    return time.monotonic() >= _edge_blocked_until


def edge_failed(cooldown: float = 120.0) -> None:
    global _edge_blocked_until
    _edge_blocked_until = time.monotonic() + cooldown


def edge_succeeded() -> None:
    global _edge_blocked_until
    _edge_blocked_until = 0.0


async def tts_edge_pcm(text: str, voice: str | None = None) -> tuple[bytes, int]:
    """Synthesize with edge-tts and decode the MP3 to 24kHz mono s16le PCM.

    edge-tts streams over a WebSocket and is much faster than the
    OpenAI-compatible gateway (which only returns the full WAV at the end),
    so the device can start speaking after the first sentence.
    """
    import asyncio

    import edge_tts
    import miniaudio

    v = voice or settings.tts_edge_voice or "zh-CN-XiaoxiaoNeural"
    comm = edge_tts.Communicate(text, v)
    data = bytearray()
    async for chunk in comm.stream():
        if chunk.get("type") == "audio":
            data += chunk.get("data", b"")
    if not data:
        raise RuntimeError("edge-tts returned no audio")
    decoded = await asyncio.to_thread(
        miniaudio.decode,
        bytes(data),
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
        sample_rate=24000,
    )
    return decoded.samples.tobytes(), 24000


def take_sentences(buf: str, *, flush: bool = False,
                   min_len: int = 10) -> tuple[list[str], str]:
    """Split a growing token buffer into speakable chunks.

    Hard sentence endings always split. Commas/colons only split once the
    pending clause is long enough, so short phrases keep natural prosody
    while long comma-only replies can still start playing early.
    """
    out: list[str] = []
    start = 0
    for i, ch in enumerate(buf):
        if ch in _SENT_END:
            piece = buf[start:i + 1].strip()
            if piece:
                out.append(piece)
            start = i + 1
        elif ch in _SOFT_END and (i + 1 - start) >= min_len:
            piece = buf[start:i + 1].strip()
            if piece:
                out.append(piece)
            start = i + 1
    rest = buf[start:]
    while len(rest) > _MAX_SENT:
        cut = max((rest.rfind(c) for c in _SOFT_END), default=-1)
        if cut < min_len:
            cut = _MAX_SENT - 1
        out.append(rest[:cut + 1].strip())
        rest = rest[cut + 1:]
    if flush and rest.strip():
        out.append(rest.strip())
        rest = ""
    return out, rest


def trim_silence(pcm: bytes, rate: int, threshold: int = 350, pad_ms: int = 50) -> bytes:
    """Trim leading/trailing silence from mono s16le PCM.

    TTS clips are padded with silence. Trimming keeps sentence-level audio
    tight so the device does not play long gaps at every sentence joint.
    """
    n = len(pcm) // 2
    if n <= 0 or rate <= 0:
        return pcm
    import array

    a = array.array("h")
    a.frombytes(pcm[: n * 2])
    win = max(1, int(rate * 0.01))          # 10ms windows
    first = last = -1
    for i in range(0, n, win):
        seg = a[i:i + win]
        if not seg:
            break
        if max(seg) > threshold or min(seg) < -threshold:
            if first < 0:
                first = i
            last = min(n, i + win)
    if first < 0:
        return b""
    pad = int(rate * pad_ms / 1000)
    start = max(0, first - pad)
    end = min(n, last + pad)
    # A quiet sentence is still speech; don't discard more than two thirds.
    if end - start < n // 3:
        return pcm
    return a[start:end].tobytes()


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
