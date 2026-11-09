"""DingTalk plugin isolation: private MCP, curated tools and plugin routes."""

from sqlalchemy import select

from conftest import auth


async def _new_user(client) -> tuple[str, int]:
    import random
    import string

    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"dt_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "testpass123"},
    )
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["user_id"]
    r = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "testpass123"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"], user_id


async def test_plugin_routes_are_mounted(client):
    token, _ = await _new_user(client)
    r = await client.get("/api/plugins/dingtalk/conversations", headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []


async def test_private_mcp_is_hidden_from_global_catalog(client):
    from core.database.session import async_session
    from ai.mcp_hub.models import McpServer
    from plugins.dingtalk.backend.service import ensure_dingtalk_server

    token, user_id = await _new_user(client)
    server = await ensure_dingtalk_server(user_id)
    assert server.scope == "internal"
    assert server.owner_plugin == "dingtalk"
    assert server.expose_tools is False
    assert server.args == ["-m", "plugins.dingtalk.mcp_server"]

    async with async_session() as db:
        row = (await db.execute(
            select(McpServer).where(McpServer.id == server.id)
        )).scalar_one()
        assert row.args == ["-m", "plugins.dingtalk.mcp_server"]

    r = await client.get("/api/mcp/servers", headers=auth(token))
    assert r.status_code == 200, r.text
    assert all(s["id"] != server.id for s in r.json()["servers"])

    r = await client.get("/api/mcp/tools", headers=auth(token))
    assert r.status_code == 200, r.text
    names = [t["name"] for t in r.json()["tools"]]
    assert not any(name.startswith(f"{server.slug}__") for name in names)
    # Curated plugin tools remain available to agents.
    assert "dingtalk_search_messages" in names
    assert "dingtalk_list_chat_members" in names
    assert not any("dws_cli" in name for name in names)


async def test_user_cannot_register_dingtalk_mcp(client):
    from sqlalchemy import select

    from core.auth.domain.models import User
    from core.database.session import async_session

    token, user_id = await _new_user(client)
    async with async_session() as db:
        row = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
        row.is_admin = True
        await db.commit()

    r = await client.post(
        "/api/mcp/servers",
        json={"name": "钉钉", "slug": "dingtalk-x", "transport": "http", "url": "http://example.com"},
        headers=auth(token),
    )
    assert r.status_code == 403, r.text


async def test_dingtalk_unread_count_controls_pending_state(client):
    from ai import context as ai_context
    from core.database.session import async_session
    from activities.models import UserActivity

    _, user_id = await _new_user(client)
    async with async_session() as db:
        db.add(UserActivity(
            user_id=user_id,
            event_type="dingtalk.conversation",
            entity_type="dingtalk",
            summary="已读群",
            details={
                "conversation": "已读群",
                "conversation_id": "conv-read",
                "unread_count": 0,
                "content": "你好",
            },
        ))
        db.add(UserActivity(
            user_id=user_id,
            event_type="dingtalk.conversation",
            entity_type="dingtalk",
            summary="未读群",
            details={
                "conversation": "未读群",
                "conversation_id": "conv-unread",
                "unread_count": 3,
                "content": "在吗",
            },
        ))
        await db.commit()

    items, _ = await ai_context.dingtalk_items(user_id, limit=10)
    by_id = {item["title"]: item for item in items}
    assert by_id["已读群"]["needs_reply"] is False
    assert by_id["已读群"]["meta"]["read"] is True
    assert by_id["未读群"]["needs_reply"] is True
    assert by_id["未读群"]["meta"]["unread_count"] == 3


async def test_conversation_ids_with_slashes_can_load_messages(client):
    from core.database.session import async_session
    from plugins.dingtalk.backend.models import DingTalkConversation, DingTalkMessage

    token, user_id = await _new_user(client)
    cid = "cid/abc+def=="
    async with async_session() as db:
        db.add(DingTalkConversation(
            user_id=user_id,
            conversation_id=cid,
            name="带特殊字符的群",
            unread_count=1,
        ))
        db.add(DingTalkMessage(
            user_id=user_id,
            conversation_id=cid,
            message_id="msg-1",
            sender="张三",
            text="你好",
        ))
        await db.commit()

    r = await client.get(
        "/api/plugins/dingtalk/messages",
        params={"conversation_id": cid},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items and items[0]["text"] == "你好"


async def test_mark_read_clears_local_unread_state(client, monkeypatch):
    from core.database.session import async_session
    from activities.models import UserActivity
    from plugins.dingtalk.backend.models import DingTalkConversation

    from plugins.dingtalk.backend import read as dingtalk_read

    async def no_message(*args, **kwargs):
        return None

    monkeypatch.setattr(dingtalk_read, "_latest_message_id", no_message)

    token, user_id = await _new_user(client)
    cid = "conv-mark-read"
    async with async_session() as db:
        db.add(DingTalkConversation(
            user_id=user_id,
            conversation_id=cid,
            name="待读群",
            unread_count=1,
        ))
        db.add(UserActivity(
            user_id=user_id,
            event_type="dingtalk.conversation",
            entity_type="dingtalk",
            summary="待读群",
            details={
                "conversation": "待读群",
                "conversation_id": cid,
                "unread_count": 1,
                "content": "消息",
            },
        ))
        await db.commit()

    r = await client.post(
        "/api/plugins/dingtalk/read",
        json={"conversation_id": cid},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text

    from sqlalchemy import select

    async with async_session() as db:
        conv = (await db.execute(
            select(DingTalkConversation).where(
                DingTalkConversation.user_id == user_id,
                DingTalkConversation.conversation_id == cid,
            )
        )).scalar_one()
        activity = (await db.execute(
            select(UserActivity).where(
                UserActivity.user_id == user_id,
                UserActivity.summary == "待读群",
            )
        )).scalar_one()
    assert conv.unread_count == 0
    assert activity.details["unread_count"] == 0
