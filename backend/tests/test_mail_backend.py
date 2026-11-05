"""Backend-first mail tests: MIME parsing, incremental sync, dedupe, API scoping."""
from datetime import datetime

from conftest import auth


async def _new_user(client) -> tuple[str, int]:
    import random
    import string

    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"mail_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "testpass123"},
    )
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["user_id"]
    r = await client.post("/api/auth/login", json={"username": username, "password": "testpass123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"], user_id


async def _create_account(client, token: str, email: str = "me@example.com") -> int:
    r = await client.post(
        "/api/plugins/mail/accounts",
        json={
            "name": "测试邮箱",
            "email": email,
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "imap_tls": True,
            "smtp_host": "smtp.example.com",
            "smtp_port": 465,
            "smtp_tls": True,
            "username": email,
            "password": "secret",
        },
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_parse_message_extracts_subject_body_and_attachment_flag():
    from plugins.mail.backend.sync import _parse_message

    raw = (
        b"From: Alice <alice@example.com>\r\n"
        b"To: me@example.com\r\n"
        b"Subject: =?utf-8?b?5ZGo5oql5o+Q6YaS?=\r\n"
        b"Date: Mon, 03 Nov 2026 09:30:00 +0800\r\n"
        b"Message-ID: <abc@example.com>\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Hello, please review the budget.\r\n"
    )
    parsed = _parse_message(raw, 101, 555)
    assert parsed["uid"] == 101
    assert parsed["uidvalidity"] == 555
    assert parsed["subject"] == "周报提醒"
    assert "Alice" in parsed["from_address"]
    assert "budget" in parsed["content"]
    assert parsed["preview"].startswith("Hello")
    assert parsed["has_attachments"] is False


async def test_sync_account_is_incremental_and_deduped(client, monkeypatch):
    from core.database.session import async_session
    from plugins.mail.backend import sync as mail_sync
    from plugins.mail.backend.models import MailMessage
    from sqlalchemy import func, select

    token, user_id = await _new_user(client)
    account_id = await _create_account(client, token)

    message = {
        "uid": 101,
        "uidvalidity": 555,
        "message_id": "<abc@example.com>",
        "subject": "预算评审",
        "from_address": "boss@example.com",
        "to_addresses": "me@example.com",
        "date": datetime(2026, 11, 3, 9, 30),
        "preview": "请今天下班前确认预算",
        "content": "请今天下班前确认预算，并回复邮件。",
        "has_attachments": False,
    }
    calls: list[int] = []

    def fake_fetch(account, password, limit=20):
        calls.append(account["last_uid"])
        return [message], 555

    monkeypatch.setattr(mail_sync, "fetch_imap_messages", fake_fetch)

    first = await mail_sync.sync_account(account_id)
    assert first["new"] == 1
    assert calls == [0]

    second = await mail_sync.sync_account(account_id)
    assert second["new"] == 0
    assert calls[-1] == 101

    async with async_session() as db:
        count = (await db.execute(
            select(func.count()).select_from(MailMessage).where(MailMessage.user_id == user_id)
        )).scalar()
        msg = (await db.execute(
            select(MailMessage).where(MailMessage.user_id == user_id)
        )).scalar_one()
    assert count == 1
    assert msg.important is False
    # Analysis is a Bot routine now; sync must not write summary/importance back.
    assert msg.ai_summary is None


async def test_mail_messages_api_is_scoped(client, monkeypatch):
    from plugins.mail.backend import sync as mail_sync

    token_a, _ = await _new_user(client)
    token_b, _ = await _new_user(client)
    account_id = await _create_account(client, token_a)

    def fake_fetch(account, password, limit=20):
        return ([{
            "uid": 7,
            "uidvalidity": 1,
            "message_id": "<m7@example.com>",
            "subject": "面试安排",
            "from_address": "hr@example.com",
            "to_addresses": "me@example.com",
            "date": datetime(2026, 11, 4, 10, 0),
            "preview": "明天下午三点面试",
            "content": "明天下午三点面试，请确认。",
            "has_attachments": False,
        }], 1)

    monkeypatch.setattr(mail_sync, "fetch_imap_messages", fake_fetch)
    assert (await mail_sync.sync_account(account_id))["new"] == 1

    r = await client.get("/api/plugins/mail/messages", headers=auth(token_a))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    msg_id = body["items"][0]["id"]
    assert body["items"][0]["subject"] == "面试安排"

    r = await client.get(f"/api/plugins/mail/messages/{msg_id}", headers=auth(token_a))
    assert r.status_code == 200
    assert "面试" in r.json()["content"]

    # Another user cannot see it.
    r = await client.get("/api/plugins/mail/messages", headers=auth(token_b))
    assert r.status_code == 200
    assert r.json()["total"] == 0
    r = await client.get(f"/api/plugins/mail/messages/{msg_id}", headers=auth(token_b))
    assert r.status_code == 404

    # Read state is persisted.
    r = await client.put(f"/api/plugins/mail/messages/{msg_id}/read", headers=auth(token_a))
    assert r.status_code == 200
    r = await client.get("/api/plugins/mail/messages?unread=true", headers=auth(token_a))
    assert r.json()["total"] == 0


async def test_account_list_hides_password_and_secret_is_owner_only(client):
    token_a, _ = await _new_user(client)
    token_b, _ = await _new_user(client)
    account_id = await _create_account(client, token_a)

    r = await client.get("/api/plugins/mail/accounts", headers=auth(token_a))
    assert r.status_code == 200, r.text
    account = next(a for a in r.json() if a["id"] == account_id)
    assert "password" not in account

    r = await client.get(
        f"/api/plugins/mail/accounts/{account_id}/secret", headers=auth(token_a)
    )
    assert r.status_code == 200, r.text
    assert r.json()["password"] == "secret"

    r = await client.get(
        f"/api/plugins/mail/accounts/{account_id}/secret", headers=auth(token_b)
    )
    assert r.status_code == 404


async def test_manual_sync_requires_ownership(client, monkeypatch):
    from plugins.mail.backend import sync as mail_sync

    token_a, _ = await _new_user(client)
    token_b, _ = await _new_user(client)
    account_id = await _create_account(client, token_a)
    monkeypatch.setattr(
        mail_sync, "fetch_imap_messages",
        lambda account, password, limit=20: ([], None),
    )

    r = await client.post(
        f"/api/plugins/mail/accounts/{account_id}/sync", headers=auth(token_b)
    )
    assert r.status_code == 404

    r = await client.post(
        f"/api/plugins/mail/accounts/{account_id}/sync", headers=auth(token_a)
    )
    assert r.status_code == 200, r.text
    assert r.json()["new"] == 0
