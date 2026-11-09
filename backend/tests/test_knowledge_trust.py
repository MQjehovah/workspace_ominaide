"""Knowledge-base trust: real document extraction, keyword fallback, vector cleanup."""
import os
import tempfile

from conftest import auth


async def _new_user(client) -> tuple[str, int]:
    import random
    import string

    suffix = "".join(random.choices(string.ascii_lowercase, k=8))
    username = f"kb_{suffix}"
    r = await client.post(
        "/api/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "testpass123"},
    )
    assert r.status_code in (200, 201), r.text
    user_id = r.json()["user_id"]
    r = await client.post("/api/auth/login", json={"username": username, "password": "testpass123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"], user_id


async def test_text_extractor_reads_docx_body():
    import docx
    from ai.retrieval.text_extractor import extract_text

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "季度预算.docx")
        d = docx.Document()
        d.add_paragraph("第三季度预算评审结论")
        d.add_paragraph("市场费用需要削减百分之十。")
        d.save(path)

        text = await extract_text(path)
        assert "第三季度预算评审结论" in text
        assert "市场费用" in text


async def test_search_falls_back_to_keywords_without_embeddings(client):
    from core.database.session import async_session
    from plugins.files.backend.models import File

    token, user_id = await _new_user(client)
    marker = f"独有词{os.urandom(3).hex()}"

    async with async_session() as db:
        db.add(File(
            user_id=user_id, bucket="user-files", object_key=f"u{user_id}/f1",
            original_name=f"{marker}-方案.pdf", is_folder=False, size=1024,
            mime_type="application/pdf", status="active", folder_path="/",
        ))
        await db.commit()

    r = await client.post(
        "/api/plugins/notes",
        json={"title": f"{marker} 会议纪要", "content": "讨论预算与排期"},
        headers=auth(token),
    )
    assert r.status_code in (200, 201), r.text

    r = await client.post(
        "/api/search", json={"q": marker, "top_k": 10}, headers=auth(token)
    )
    assert r.status_code == 200, r.text
    types = {x["type"] for x in r.json()["results"]}
    assert "file" in types
    assert "note" in types


async def test_deleting_note_cleans_semantic_index(client, monkeypatch):
    from ai.retrieval import vector_store

    token, _ = await _new_user(client)
    r = await client.post(
        "/api/plugins/notes",
        json={"title": "待删除", "content": "临时内容"},
        headers=auth(token),
    )
    assert r.status_code in (200, 201), r.text
    note_id = r.json()["id"]

    deleted: list[tuple] = []

    async def fake_delete_source(user_id, source_type, source_id):
        deleted.append((user_id, source_type, source_id))

    monkeypatch.setattr(vector_store, "delete_source", fake_delete_source)

    r = await client.delete(f"/api/plugins/notes/{note_id}", headers=auth(token))
    assert r.status_code == 200, r.text
    assert any(d[1] == "note" and d[2] == note_id for d in deleted)
