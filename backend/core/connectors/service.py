"""Connector accounts, encrypted token storage and token refresh."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from core.config.settings import settings
from core.crypto import decrypt_secret, encrypt_secret
from core.database.session import async_session
from core.connectors.models import ConnectorAccount
from core.connectors.providers import get_provider


def is_configured(provider: str) -> bool:
    if provider == "google":
        return bool(settings.google_client_id and settings.google_client_secret)
    return False


def account_dict(account: ConnectorAccount) -> dict:
    return {
        "id": account.id,
        "provider": account.provider,
        "account_id": account.account_id,
        "email": account.email,
        "name": account.name,
        "scopes": account.scopes or [],
        "status": account.status,
        "expires_at": account.expires_at.isoformat() if account.expires_at else None,
        "created_at": account.created_at.isoformat() if account.created_at else None,
    }


async def list_accounts(user_id: int, provider: str | None = None) -> list[ConnectorAccount]:
    async with async_session() as db:
        q = select(ConnectorAccount).where(ConnectorAccount.user_id == user_id)
        if provider:
            q = q.where(ConnectorAccount.provider == provider)
        rows = await db.execute(q.order_by(ConnectorAccount.id.asc()))
        return list(rows.scalars().all())


async def get_account(
    user_id: int,
    provider: str,
    account_id: int | None = None,
) -> ConnectorAccount | None:
    async with async_session() as db:
        q = select(ConnectorAccount).where(
            ConnectorAccount.user_id == user_id,
            ConnectorAccount.provider == provider,
        )
        if account_id is not None:
            q = q.where(ConnectorAccount.id == account_id)
        q = q.order_by(ConnectorAccount.id.asc()).limit(1)
        return (await db.execute(q)).scalar_one_or_none()


async def save_account(
    user_id: int,
    provider: str,
    account_id: str,
    *,
    email: str | None,
    name: str | None,
    access_token: str,
    refresh_token: str | None,
    scopes: list[str],
    expires_at: datetime | None,
) -> ConnectorAccount:
    async with async_session() as db:
        row = (await db.execute(
            select(ConnectorAccount).where(
                ConnectorAccount.user_id == user_id,
                ConnectorAccount.provider == provider,
                ConnectorAccount.account_id == account_id,
            )
        )).scalar_one_or_none()
        if row is None:
            row = ConnectorAccount(
                user_id=user_id,
                provider=provider,
                account_id=account_id,
            )
            db.add(row)
        row.email = email
        row.name = name
        row.access_token = encrypt_secret(access_token)
        row.refresh_token = encrypt_secret(refresh_token or "")
        row.scopes = scopes
        row.expires_at = expires_at
        row.status = "active"
        await db.commit()
        await db.refresh(row)
        return row


async def disconnect(user_id: int, account_id: int) -> bool:
    async with async_session() as db:
        row = (await db.execute(
            select(ConnectorAccount).where(
                ConnectorAccount.id == account_id,
                ConnectorAccount.user_id == user_id,
            )
        )).scalar_one_or_none()
        if row is None:
            return False
        await db.delete(row)
        await db.commit()
        return True


async def get_access_token(
    user_id: int,
    provider: str,
    account_id: int | None = None,
) -> tuple[str, ConnectorAccount]:
    account = await get_account(user_id, provider, account_id)
    if account is None:
        raise ConnectorError(
            f"还没有连接 {get_provider(provider).name if get_provider(provider) else provider} 账号"
        )
    token = decrypt_secret(account.access_token)
    if account.expires_at and account.expires_at > datetime.now() + timedelta(seconds=60):
        return token, account
    refresh = decrypt_secret(account.refresh_token or "")
    if not refresh:
        raise ConnectorError("连接已过期，请重新授权")
    try:
        if provider == "google":
            from core.connectors import google

            data = await google.refresh_access_token(refresh)
        else:
            raise ConnectorError("该连接器不支持刷新 token")
    except Exception as exc:
        raise ConnectorError(f"刷新授权失败：{exc}") from exc
    token = str(data.get("access_token") or "")
    if not token:
        raise ConnectorError("刷新授权失败：没有拿到 access_token")
    expires_at = datetime.now() + timedelta(seconds=int(data.get("expires_in") or 3600))
    async with async_session() as db:
        row = await db.get(ConnectorAccount, account.id)
        if row is not None:
            row.access_token = encrypt_secret(token)
            if data.get("refresh_token"):
                row.refresh_token = encrypt_secret(str(data["refresh_token"]))
            row.expires_at = expires_at
            row.status = "active"
            await db.commit()
            await db.refresh(row)
            account = row
    return token, account


class ConnectorError(RuntimeError):
    pass
