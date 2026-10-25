from conftest import auth


async def test_notes_rag_index_search_and_status(client, admin_token):
    """Notes are chunked/indexed and hybrid search returns the right note."""
    r = await client.post(
        "/api/plugins/notes",
        json={
            "title": "Q3 预算方案",
            "content": (
                "# Q3 预算方案\n\n"
                "下周五前完成 Q3 预算方案，重点是与张三讨论服务器采购。\n\n"
                "## 采购\n\n服务器预算 5 万元，用于购买两台 GPU 服务器。\n\n"
                "## 风险\n\n预算可能被削减，需要准备备选方案。"
            ),
        },
        headers=auth(admin_token),
    )
    assert r.status_code == 201, r.text
    note_id = r.json()["id"]

    r = await client.post(
        "/api/plugins/notes/rag/reindex",
        json={"limit": 50},
        headers=auth(admin_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["notes"] >= 1
    assert r.json()["chunks"] >= 1
    assert r.json()["terms"] >= 1

    r = await client.get(
        "/api/plugins/notes/rag/status", headers=auth(admin_token)
    )
    assert r.status_code == 200
    assert r.json()["chunks"] >= 1

    r = await client.post(
        "/api/plugins/notes/rag/search",
        json={"q": "服务器采购 预算"},
        headers=auth(admin_token),
    )
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    assert results
    assert any(n["note_id"] == note_id for n in results)
    assert any("预算" in n["title"] for n in results)

    # Unrelated query should not crash (may be empty).
    r = await client.post(
        "/api/plugins/notes/rag/search",
        json={"q": "火星殖民计划"},
        headers=auth(admin_token),
    )
    assert r.status_code == 200
    assert isinstance(r.json()["results"], list)


async def test_notes_rag_mcp_tools_registered(client, admin_token):
    r = await client.get("/api/mcp/tools", headers=auth(admin_token))
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["tools"]}
    assert "ask_notes" in names
    assert "search_notes_semantic" in names
    assert "set_device_timer" in names


async def test_device_events_longpoll_returns_published_event(client, admin_token):
    """Proactive notifications are delivered to hardware devices via long-poll."""
    from core.auth.jwt import decode_access_token
    from plugins.device.backend.events import publish_device_event

    uid = int(decode_access_token(admin_token)["sub"])
    await publish_device_event(uid, "notification", {
        "title": "测试提醒",
        "body": "来自后台的实时事件",
    })

    r = await client.get(
        "/api/device/events?since=0&wait=0", headers=auth(admin_token)
    )
    assert r.status_code == 200, r.text
    events = r.json()["events"]
    assert any(e["type"] == "notification" for e in events)
    assert events[-1]["id"] >= 1

    # since=-1 is a cursor sync: no replay, just the latest id
    r = await client.get(
        "/api/device/events?since=-1&wait=0", headers=auth(admin_token)
    )
    assert r.status_code == 200
    assert r.json()["events"] == []
    assert r.json()["last_id"] >= 1

    # Web/mobile -> device push endpoint
    r = await client.post(
        "/api/device/push",
        json={"title": "到家提醒", "body": "记得关窗"},
        headers=auth(admin_token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert r.json()["event"]["title"] == "到家提醒"
