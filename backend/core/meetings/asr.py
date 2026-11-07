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


def _post(file_record, diarize: bool) -> dict:
    from core.minio.client import minio_client

    if minio_client is None:
        raise AsrError("MinIO 不可用，无法读取录音")

    api_key = settings.asr_api_key or settings.llm_api_key
    if not api_key:
        raise AsrError("未配置 ASR API Key")

    headers = {"Authorization": f"Bearer {api_key}"}
    data = {
        "model": settings.asr_model,
        "response_format": "verbose_json",
    }
    if diarize:
        data["diarize"] = "true"

    response = minio_client.get_object(file_record.bucket, file_record.object_key)
    try:
        timeout = httpx.Timeout(
            connect=30.0,
            read=float(settings.asr_timeout_seconds),
            write=float(settings.asr_timeout_seconds),
            pool=30.0,
        )
        with httpx.Client(timeout=timeout) as client:
            res = client.post(
                _endpoint(),
                headers=headers,
                data=data,
                files={
                    "file": (
                        file_record.original_name or "meeting.m4a",
                        response,
                        file_record.mime_type or "application/octet-stream",
                    )
                },
            )
            if res.status_code >= 400:
                # Some OpenAI-compatible servers reject verbose_json/diarize.
                if diarize or "response_format" in data:
                    retry_data = {"model": settings.asr_model}
                    res = client.post(
                        _endpoint(),
                        headers=headers,
                        data=retry_data,
                        files={
                            "file": (
                                file_record.original_name or "meeting.m4a",
                                response,
                                file_record.mime_type
                                or "application/octet-stream",
                            )
                        },
                    )
            if res.status_code >= 400:
                raise AsrError(
                    f"ASR 返回 {res.status_code}: {res.text[:500]}"
                )
            content_type = res.headers.get("content-type", "")
            if "json" in content_type:
                return _normalise(res.json())
            return _normalise(res.text)
    finally:
        try:
            response.close()
        except Exception:
            pass


async def transcribe_minio_object(file_record, *, diarize: bool | None = None) -> dict:
    """Transcribe a MinIO file object without copying it through a temp file."""
    if diarize is None:
        diarize = settings.asr_diarize
    try:
        return await asyncio.to_thread(_post, file_record, diarize)
    except AsrError:
        raise
    except Exception as exc:
        raise AsrError(f"语音转写失败: {exc}") from exc
