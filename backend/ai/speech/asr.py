"""Stream the original MinIO audio object into the configured ASR service.

No second copy is uploaded to the backend, and no local temp file is created:
the MinIO response is handed to httpx as the multipart file stream.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from core.config.settings import settings


class AsrError(RuntimeError):
    pass


def _endpoint() -> str:
    return settings.asr_base_url.rstrip("/") + "/audio/transcriptions"


def _normalise(payload: Any) -> dict:
    if isinstance(payload, str):
        return {"text": payload.strip(), "segments": []}
    if not isinstance(payload, dict):
        return {"text": "", "segments": []}

    text = str(payload.get("text") or "").strip()
    if not text:
        result = payload.get("result")
        if isinstance(result, dict):
            text = str(result.get("text") or result.get("transcript") or "").strip()
        elif isinstance(result, str):
            text = result.strip()

    raw_segments = payload.get("segments") or payload.get("utterances")
    if not raw_segments:
        result = payload.get("result")
        if isinstance(result, dict):
            raw_segments = result.get("segments") or result.get("utterances")
    segments: list[dict] = []
    for row in raw_segments or []:
        if not isinstance(row, dict):
            continue
        value = str(row.get("text") or row.get("content") or "").strip()
        if not value:
            continue
        segments.append(
            {
                "start": row.get("start", row.get("start_time")),
                "end": row.get("end", row.get("end_time")),
                "speaker": row.get("speaker")
                or row.get("speaker_id")
                or row.get("spk")
                or row.get("channel"),
                "text": value,
            }
        )
    return {"text": text, "segments": segments}


class _SizedStream:
    """Expose an exact length to httpx without copying the MinIO object."""

    def __init__(self, response, size: int):
        self.response = response
        self.size = max(0, int(size or 0))
        self._pos = 0

    def read(self, n: int = -1) -> bytes:
        data = self.response.read(n)
        self._pos += len(data or b"")
        return data

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 2:
            return self.size
        return offset

    def close(self) -> None:
        try:
            self.response.close()
        except Exception:
            pass


def _post(
    file_record,
    diarize: bool,
    model: str,
    verbose: bool,
) -> dict:
    from core.minio.client import minio_client

    if minio_client is None:
        raise AsrError("MinIO 不可用，无法读取录音")

    api_key = settings.asr_api_key or settings.llm_api_key
    if not api_key:
        raise AsrError("未配置 ASR API Key")

    size = int(file_record.size or 0)
    if size <= 0:
        try:
            size = int(
                minio_client.stat_object(
                    file_record.bucket, file_record.object_key
                ).size
            )
        except Exception:
            size = 0

    headers = {"Authorization": f"Bearer {api_key}"}
    timeout = httpx.Timeout(
        connect=30.0,
        read=float(settings.asr_timeout_seconds),
        write=float(settings.asr_timeout_seconds),
        pool=30.0,
    )

    def attempt(data: dict) -> httpx.Response:
        raw = minio_client.get_object(file_record.bucket, file_record.object_key)
        stream = _SizedStream(raw, size)
        try:
            with httpx.Client(timeout=timeout) as client:
                return client.post(
                    _endpoint(),
                    headers=headers,
                    data=data,
                    files={
                        "file": (
                            file_record.original_name or "meeting.m4a",
                            stream,
                            file_record.mime_type or "application/octet-stream",
                        )
                    },
                )
        finally:
            stream.close()

    data = {"model": model}
    if verbose:
        data["response_format"] = "verbose_json"
    if diarize:
        data["diarize"] = "true"

    res = attempt(data)
    if res.status_code >= 400 and len(data) > 1:
        # Some OpenAI-compatible servers reject verbose_json/diarize.
        res = attempt({"model": model})
    if res.status_code >= 400:
        raise AsrError(f"ASR 返回 {res.status_code}: {res.text[:500]}")
    content_type = res.headers.get("content-type", "")
    if "json" in content_type:
        return _normalise(res.json())
    return _normalise(res.text)



async def transcribe_minio_object(
    file_record,
    *,
    diarize: bool | None = None,
    model: str | None = None,
    verbose: bool | None = None,
) -> dict:
    """Transcribe a MinIO file object without copying it through a temp file.

    Meetings use ``voice-asr-moss`` with ``verbose_json`` so long recordings
    (over the 300s limit of the default model) come back as speaker segments.
    """
    if diarize is None:
        diarize = settings.asr_diarize
    if model is None:
        model = settings.asr_model
    if verbose is None:
        verbose = settings.asr_verbose_json
    from core.observability.recorder import trace_span

    try:
        async with trace_span("asr", file_record.original_name or "meeting"):
            return await asyncio.to_thread(
                _post, file_record, diarize, model, verbose
            )
    except AsrError:
        raise
    except Exception as exc:
        raise AsrError(f"语音转写失败: {exc}") from exc
