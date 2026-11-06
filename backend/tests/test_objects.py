"""Business object references and threaded comments."""
from conftest import auth


async def test_business_object_search_and_threaded_comments(client, admin_token):
    note = await client.post(
        "/api/plugins/notes",
        json={"title": "对象测试笔记", "content": "用于搜索和评论的业务对象"},
        headers=auth(admin_token),
    )
    assert note.status_code == 201, note.text
    note_id = note.json()["id"]

    todo = await client.post(
        "/api/plugins/todo/items",
        json={"title": "对象测试待办"},
        headers=auth(admin_token),
    )
    assert todo.status_code == 201, todo.text

    r = await client.get(
        "/api/objects/search",
        params={"q": "对象测试", "types": "note,todo"},
        headers=auth(admin_token),
    )
    assert r.status_code == 200, r.text
    types = {item["type"] for item in r.json()["items"]}
    assert {"note", "todo"} <= types

    r = await client.get(f"/api/objects/note/{note_id}", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "对象测试笔记"
    assert r.json()["url"].startswith("/notes")

    root = await client.post(
        f"/api/objects/note/{note_id}/comments",
        json={"kind": "note", "content": "这是一条备注", "title": "备注标题"},
        headers=auth(admin_token),
    )
    assert root.status_code == 201, root.text
    root_id = root.json()["id"]

    reply = await client.post(
        f"/api/objects/note/{note_id}/comments",
        json={"kind": "comment", "content": "这是回复", "parent_id": root_id},
        headers=auth(admin_token),
    )
    assert reply.status_code == 201, reply.text
    assert reply.json()["parent_id"] == root_id
    assert reply.json()["root_id"] == root_id

    r = await client.get(
        f"/api/objects/note/{note_id}/comments", headers=auth(admin_token)
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["items"]) == 2

    r = await client.delete(f"/api/objects/comments/{root_id}", headers=auth(admin_token))
    assert r.status_code == 200, r.text

    r = await client.get(
        f"/api/objects/note/{note_id}/comments", headers=auth(admin_token)
    )
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == reply.json()["id"]
    assert items[0]["parent_id"] == root_id


async def test_chat_context_block_includes_object(client, admin_token):
    from core.auth.jwt import decode_access_token
    from core.objects.registry import build_context_block

    note = await client.post(
        "/api/plugins/notes",
        json={"title": "聊天上下文对象", "content": "上下文测试正文"},
        headers=auth(admin_token),
    )
    note_id = note.json()["id"]
    user_id = int(decode_access_token(admin_token)["sub"])

    block = await build_context_block(
        user_id, [{"type": "note", "id": note_id}], None
    )
    assert block
    assert "聊天上下文对象" in block
    assert "comment_business_object" in block
