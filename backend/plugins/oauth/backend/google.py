"""Google OAuth and read/write helpers for Gmail, Calendar and Drive."""

from __future__ import annotations

import base64
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from urllib.parse import quote, urlencode

import httpx

from core.config.settings import settings
from plugins.oauth.backend.providers import get_provider


class GoogleError(RuntimeError):
    pass


def _require_client() -> tuple[str, str]:
    if not settings.google_client_id or not settings.google_client_secret:
        raise GoogleError("Google OAuth 未配置（GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET）")
    return settings.google_client_id, settings.google_client_secret


def authorization_url(*, state: str, code_challenge: str, redirect_uri: str) -> str:
    client_id, _ = _require_client()
    scopes = get_provider("google").scopes if get_provider("google") else []
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)


async def _token_request(data: dict) -> dict:
    client_id, client_secret = _require_client()
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        **data,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post("https://oauth2.googleapis.com/token", data=payload)
    if resp.status_code != 200:
        raise GoogleError(f"OAuth token 失败：{resp.text[:300]}")
    return resp.json()


async def exchange_code(*, code: str, code_verifier: str, redirect_uri: str) -> dict:
    return await _token_request({
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })


async def refresh_access_token(refresh_token: str) -> dict:
    return await _token_request({
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })


async def userinfo(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        raise GoogleError(f"获取 Google 用户信息失败：{resp.text[:300]}")
    return resp.json()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _get_json(token: str, url: str, params: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=_auth(token), params=params)
    if resp.status_code >= 400:
        raise GoogleError(f"Google API {resp.status_code}：{resp.text[:300]}")
    return resp.json()


async def _post_json(token: str, url: str, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=_auth(token), json=payload)
    if resp.status_code >= 400:
        raise GoogleError(f"Google API {resp.status_code}：{resp.text[:300]}")
    return resp.json()


# ---------------------------------------------------------------------------
# Gmail
# ---------------------------------------------------------------------------

def _header(payload: dict, name: str) -> str:
    for item in payload.get("headers") or []:
        if str(item.get("name", "")).lower() == name.lower():
            return str(item.get("value") or "")
    return ""


def _decode_body(payload: dict) -> str:
    data = payload.get("body", {}).get("data")
    if data:
        try:
            return base64.urlsafe_b64decode(data + "===").decode("utf-8", "replace")
        except Exception:
            return ""
    for part in payload.get("parts") or []:
        mime = str(part.get("mimeType") or "")
        if mime.startswith("text/plain"):
            text = _decode_body(part)
            if text:
                return text
    for part in payload.get("parts") or []:
        text = _decode_body(part)
        if text:
            return text
    return ""


async def gmail_search(token: str, query: str, limit: int = 10) -> list[dict]:
    data = await _get_json(
        token,
        "https://gmail.googleapis.com/gmail/v1/users/me/messages",
        {"q": query, "maxResults": max(1, min(limit, 20))},
    )
    out = []
    for item in (data.get("messages") or [])[:limit]:
        msg = await _get_json(
            token,
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{item['id']}",
            {"format": "metadata", "metadataHeaders": ["From", "To", "Subject", "Date"]},
        )
        payload = msg.get("payload") or {}
        out.append({
            "id": msg.get("id"),
            "thread_id": msg.get("threadId"),
            "from": _header(payload, "From"),
            "to": _header(payload, "To"),
            "subject": _header(payload, "Subject"),
            "date": _header(payload, "Date"),
            "snippet": msg.get("snippet") or "",
        })
    return out


async def gmail_read(token: str, message_id: str) -> dict:
    msg = await _get_json(
        token,
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
        {"format": "full"},
    )
    payload = msg.get("payload") or {}
    return {
        "id": msg.get("id"),
        "thread_id": msg.get("threadId"),
        "from": _header(payload, "From"),
        "to": _header(payload, "To"),
        "cc": _header(payload, "Cc"),
        "subject": _header(payload, "Subject"),
        "date": _header(payload, "Date"),
        "body": _decode_body(payload)[:100_000],
        "labels": msg.get("labelIds") or [],
    }


async def gmail_send(
    token: str,
    *,
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
) -> dict:
    message = EmailMessage()
    message["To"] = to
    if cc:
        message["Cc"] = cc
    message["Subject"] = subject
    message.set_content(body or "")
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    return await _post_json(
        token,
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        {"raw": raw},
    )


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

def _iso(value: str | None, fallback: datetime) -> str:
    if value:
        return value
    return fallback.isoformat(timespec="seconds")


async def calendar_list(
    token: str,
    *,
    time_min: str | None = None,
    time_max: str | None = None,
    limit: int = 20,
) -> list[dict]:
    now = datetime.now().astimezone()
    data = await _get_json(
        token,
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        {
            "timeMin": _iso(time_min, now),
            "timeMax": _iso(time_max, now + timedelta(days=7)),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": max(1, min(limit, 50)),
        },
    )
    out = []
    for event in data.get("items") or []:
        start = event.get("start") or {}
        end = event.get("end") or {}
        out.append({
            "id": event.get("id"),
            "summary": event.get("summary") or "（无标题）",
            "start": start.get("dateTime") or start.get("date"),
            "end": end.get("dateTime") or end.get("date"),
            "location": event.get("location") or "",
            "description": event.get("description") or "",
            "html_link": event.get("htmlLink") or "",
        })
    return out


async def calendar_create(
    token: str,
    *,
    summary: str,
    start: str,
    end: str,
    description: str | None = None,
    location: str | None = None,
) -> dict:
    payload = {
        "summary": summary,
        "start": {"dateTime": start},
        "end": {"dateTime": end},
    }
    if description:
        payload["description"] = description
    if location:
        payload["location"] = location
    return await _post_json(
        token,
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        payload,
    )


# ---------------------------------------------------------------------------
# Drive
# ---------------------------------------------------------------------------

async def drive_search(token: str, query: str, limit: int = 10) -> list[dict]:
    q = (query or "").strip()
    if q and "contains" not in q.lower():
        q = "name contains '" + q.replace("'", "\\'") + "'"
    data = await _get_json(
        token,
        "https://www.googleapis.com/drive/v3/files",
        {
            "q": q or None,
            "pageSize": max(1, min(limit, 30)),
            "fields": "files(id,name,mimeType,modifiedTime,size,webViewLink,parents)",
            "orderBy": "modifiedTime desc",
        },
    )
    return list(data.get("files") or [])


async def drive_read(token: str, file_id: str) -> dict:
    meta = await _get_json(
        token,
        f"https://www.googleapis.com/drive/v3/files/{file_id}",
        {"fields": "id,name,mimeType,size,modifiedTime,webViewLink"},
    )
    mime = str(meta.get("mimeType") or "")
    if mime.startswith("application/vnd.google-apps"):
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
                headers=_auth(token),
                params={"mimeType": "text/plain"},
            )
        if resp.status_code >= 400:
            raise GoogleError(f"导出 Google 文档失败：{resp.text[:300]}")
        return {**meta, "content": resp.text[:200_000], "binary": False}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            headers=_auth(token),
            params={"alt": "media"},
        )
    if resp.status_code >= 400:
        raise GoogleError(f"下载文件失败：{resp.text[:300]}")
    raw = resp.content[:2_000_000]
    binary = b"\x00" in raw[:8192]
    return {
        **meta,
        "content": "" if binary else raw.decode("utf-8", "replace"),
        "binary": binary,
        "truncated": len(resp.content) > len(raw),
    }


async def drive_upload(
    token: str,
    *,
    name: str,
    content: bytes,
    mime_type: str = "application/octet-stream",
) -> dict:
    boundary = "omniaide-boundary-" + base64.urlsafe_b64encode(content[:9]).decode().rstrip("=")
    meta = ('{"name": "' + name.replace('"', '\\"') + '"}').encode("utf-8")
    body = (
        b"--" + boundary.encode() + b"\r\n"
        b"Content-Type: application/json; charset=UTF-8\r\n\r\n" + meta + b"\r\n"
        b"--" + boundary.encode() + b"\r\n"
        b"Content-Type: " + mime_type.encode() + b"\r\n\r\n" + content + b"\r\n"
        b"--" + boundary.encode() + b"--\r\n"
    )
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://www.googleapis.com/upload/drive/v3/files",
            headers={
                **_auth(token),
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
            params={"uploadType": "multipart", "fields": "id,name,mimeType,webViewLink"},
            content=body,
        )
    if resp.status_code >= 400:
        raise GoogleError(f"上传到 Drive 失败：{resp.text[:300]}")
    return resp.json()
