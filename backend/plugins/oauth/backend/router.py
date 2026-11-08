"""OAuth plugin routes: authorize external accounts and manage tokens."""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from core.auth.dependencies import get_current_user
from core.cache import delete, get_json, set_json
from core.config.settings import settings
from plugins.oauth.backend import service
from plugins.oauth.backend.providers import PROVIDERS, get_provider

router = APIRouter(prefix="/api/oauth", tags=["oauth"])

STATE_TTL = 600


class StartOAuthRequest(BaseModel):
    provider: str = "google"


def _provider_out(provider_key: str, provider, accounts: list) -> dict:
    return {
        "key": provider_key,
        "name": provider.name,
        "description": provider.description,
        "configured": service.is_configured(provider_key),
        "scopes": provider.scopes,
        "accounts": accounts,
    }


@router.get("")
async def list_providers(user: dict = Depends(get_current_user)):
    """List external authorization providers and the user's connected accounts."""
    accounts = await service.list_accounts(user["id"])
    grouped: dict[str, list] = {}
    for account in accounts:
        grouped.setdefault(account.provider, []).append(service.account_dict(account))
    providers = [
        _provider_out(key, provider, grouped.get(key, []))
        for key, provider in PROVIDERS.items()
    ]
    return {"providers": providers}


# ---------------------------------------------------------------------------
# OAuth flow
# ---------------------------------------------------------------------------

def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def _redirect_uri(request: Request) -> str:
    base = (settings.oauth_redirect_base or "").strip()
    if not base:
        base = str(request.base_url).rstrip("/") + "/api"
    return base.rstrip("/") + "/oauth/callback"


def _frontend_redirect(status: str, provider: str, message: str | None = None) -> str:
    base = settings.app_base_url.rstrip("/")
    params = {"tab": "connectors", "connector": provider, "status": status}
    if message:
        params["message"] = message[:300]
    return f"{base}/settings?{urlencode(params)}"


@router.post("/start")
async def start_oauth(
    req: StartOAuthRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    provider = (req.provider or "google").strip().lower()
    if get_provider(provider) is None:
        raise HTTPException(status_code=404, detail="未知的外部授权插件")
    if not service.is_configured(provider):
        raise HTTPException(
            status_code=400,
            detail=f"{provider} OAuth 未配置，请先设置客户端 ID 和密钥",
        )
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(32)
    redirect_uri = _redirect_uri(request)
    await set_json(
        f"oauth:{state}",
        {
            "user_id": user["id"],
            "provider": provider,
            "verifier": verifier,
            "redirect_uri": redirect_uri,
        },
        ttl_seconds=STATE_TTL,
    )
    from plugins.oauth.backend import google

    url = google.authorization_url(
        state=state,
        code_challenge=challenge,
        redirect_uri=redirect_uri,
    )
    return {"provider": provider, "auth_url": url, "state": state}


@router.get("/callback")
async def oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    provider = "google"
    if error:
        return RedirectResponse(_frontend_redirect("error", provider, error))
    if not code or not state:
        raise HTTPException(status_code=400, detail="缺少 code 或 state")

    data = await get_json(f"oauth:{state}")
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="授权状态已过期，请重试")
    await delete(f"oauth:{state}")

    provider = str(data.get("provider") or "google")
    user_id = int(data.get("user_id") or 0)
    verifier = str(data.get("verifier") or "")
    redirect_uri = str(data.get("redirect_uri") or "")
    if not user_id:
        raise HTTPException(status_code=400, detail="无效的授权状态")

    try:
        if provider == "google":
            from plugins.oauth.backend import google

            token = await google.exchange_code(
                code=code, code_verifier=verifier, redirect_uri=redirect_uri
            )
            access = str(token.get("access_token") or "")
            refresh = str(token.get("refresh_token") or "")
            if not access:
                raise RuntimeError("没有拿到 access_token")
            info = await google.userinfo(access)
            account_id = str(info.get("sub") or info.get("email") or "")
            if not account_id:
                raise RuntimeError("没有拿到 Google 账号 ID")
            scopes = str(token.get("scope") or "").split()
            expires_at = datetime.now() + timedelta(
                seconds=int(token.get("expires_in") or 3600)
            )
            await service.save_account(
                user_id,
                provider,
                account_id,
                email=str(info.get("email") or "") or None,
                name=str(info.get("name") or "") or None,
                access_token=access,
                refresh_token=refresh or None,
                scopes=scopes,
                expires_at=expires_at,
            )
        else:
            raise RuntimeError("该外部授权插件暂不支持")
    except Exception as exc:
        return RedirectResponse(
            _frontend_redirect("error", provider, str(exc))
        )

    return RedirectResponse(_frontend_redirect("ok", provider))


@router.delete("/{account_id}")
async def disconnect_account(
    account_id: int,
    user: dict = Depends(get_current_user),
):
    ok = await service.disconnect(user["id"], account_id)
    if not ok:
        raise HTTPException(status_code=404, detail="连接不存在")
    return {"message": "已断开连接"}
