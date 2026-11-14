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

try:
    import audioop  # Python 3.12; removed in 3.13
except ImportError:  # pragma: no cover
    audioop = None

import httpx
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


async def tts_gateway_stream(
    text: str,
    voice: str | None = None,
    url: str | None = None,
    api_key: str | None = None,
) -> AsyncIterator[tuple[bytes, int]]:
    """Stream PCM16 chunks from the gateway's frame protocol.

    The endpoint returns ``application/vnd.evs.pcm16-frames``:
    ``tag(1B) | length(4B big-endian) | payload`` where ``A`` is audio,
    ``E`` is end and ``X`` is an error frame.
    """
    target = url or settings.tts_stream_url
    if not target:
        return
    key = api_key or settings.tts_api_key or settings.llm_api_key
    body = {
        "model": settings.tts_model,
        "input": text,
        "voice": voice or settings.tts_voice,
    }
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    timeout = httpx.Timeout(300.0, connect=10.0, read=120.0, write=60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", target, json=body, headers=headers) as response:
            if response.status_code != 200:
                detail = (await response.aread())[:300]
                raise RuntimeError(f"TTS stream HTTP {response.status_code}: {detail!r}")
            try:
                rate = int(response.headers.get("x-audio-sample-rate") or 24000)
            except ValueError:
                rate = 24000

            buf = bytearray()
            conv_state = None
            async for chunk in response.aiter_bytes():
                if not chunk:
                    continue
                buf.extend(chunk)
                while True:
                    if len(buf) < 5:
                        break
                    tag = buf[0]
                    length = int.from_bytes(buf[1:5], "big")
                    if len(buf) < 5 + length:
                        break
                    payload = bytes(buf[5:5 + length])
                    del buf[:5 + length]
                    if tag == 0x41:
                        if not payload:
                            continue
                        out, out_rate = payload, rate
                        if rate != 16000 and audioop is not None:
                            try:
                                out, conv_state = audioop.ratecv(
                                    payload, 2, 1, rate, 16000, conv_state
                                )
                                out_rate = 16000
                            except Exception:
                                out, out_rate = payload, rate
                        if out:
                            yield out, out_rate
                    elif tag == 0x45:
                        return
                    elif tag == 0x58:
                        msg = payload.decode("utf-8", "replace")
                        raise RuntimeError(f"TTS stream error frame: {msg[:200]}")
                    else:
                        raise RuntimeError(f"bad TTS frame tag 0x{tag:02x}")


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


SENTENCE_END = "。！？!?.;；\n…"
SOFT_BREAK = "，,、：:"


class SentenceChunker:
    """Turn a token stream into short speakable chunks.

    The first chunk should arrive as early as possible, so long clauses are
    split at a comma once they exceed ``soft_limit`` characters. This lets TTS
    start while the model is still generating the rest of the answer.
    """

    def __init__(self, soft_limit: int = 26, hard_limit: int = 64, first_limit: int = 16):
        self.buf = ""
        self.soft_limit = soft_limit
        self.hard_limit = hard_limit
        # The first chunk is synthesized while the model is still talking, so
        # keep it short: lower first-audio latency without chopping every
        # sentence into unnatural pieces.
        self.first_limit = first_limit
        self.started = False

    def push(self, text: str) -> list[str]:
        self.buf += text
        out: list[str] = []
        while True:
            buf = self.buf
            cut = -1
            for i, ch in enumerate(buf):
                if ch in SENTENCE_END:
                    cut = i + 1
                    break
            if cut > 0:
                out.append(buf[:cut])
                self.buf = buf[cut:]
                continue
            limit = self.soft_limit if (self.started or out) else self.first_limit
            if len(buf) >= limit:
                last = max((buf.rfind(ch) for ch in SOFT_BREAK), default=-1)
                if last >= 6:
                    out.append(buf[:last + 1])
                    self.buf = buf[last + 1:]
                    continue
            hard = self.hard_limit if (self.started or out) else max(24, self.first_limit + 8)
            if len(buf) >= hard:
                out.append(buf)
                self.buf = ""
                continue
            break
        if out:
            self.started = True
        return [chunk.strip() for chunk in out if chunk.strip()]

    def flush(self) -> list[str]:
        chunk = self.buf.strip()
        self.buf = ""
        return [chunk] if chunk else []
