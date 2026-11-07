"""Voice helpers for the device endpoint.

The device uploads one recorded utterance, the server runs ASR + the agent,
then synthesizes the reply and emits NDJSON frames:

  transcript -> delta/status -> PCM chunks -> done

The TTS gateway is synchronous (it returns the complete WAV at the end), so
the device buffers the reply and plays it as one continuous clip.
"""
from __future__ import annotations

import json
from typing import AsyncIterator

from openai import AsyncOpenAI

from core.config.settings import settings


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
