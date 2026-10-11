"""pgvector-backed vector store, replacing Qdrant.

All collections live in a single table `embeddings`, distinguished by the
`collection` column (previously Qdrant collections: file_embeddings, omnidocs,
entities). Similarity uses pgvector's cosine distance operator `<=>`.
"""
from __future__ import annotations

import json

from sqlalchemy import bindparam, text

from core.config.settings import settings
from core.database.session import engine

DIM = int(getattr(settings, "embedding_dimensions", 1024) or 1024)

_ensured = False


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


async def ensure_vector_schema() -> None:
    global _ensured
    if _ensured:
        return
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text(
            f"""
            CREATE TABLE IF NOT EXISTS embeddings (
                id BIGSERIAL PRIMARY KEY,
                collection TEXT NOT NULL,
                doc_key TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                source_type TEXT,
                source_id INTEGER,
                title TEXT,
                content TEXT,
                metadata JSONB,
                embedding vector({DIM}) NOT NULL,
                created_at TIMESTAMP DEFAULT now(),
                UNIQUE (collection, doc_key)
            )
            """
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS embeddings_collection_user_idx "
            "ON embeddings (collection, user_id)"
        ))
    _ensured = True


async def upsert(
    collection: str,
    doc_key: str,
    user_id: int,
    embedding: list[float],
    *,
    source_type: str | None = None,
    source_id: int | None = None,
    title: str | None = None,
    content: str | None = None,
    metadata: dict | None = None,
) -> None:
    await ensure_vector_schema()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO embeddings
                    (collection, doc_key, user_id, source_type, source_id, title, content, metadata, embedding)
                VALUES
                    (:collection, :doc_key, :user_id, :source_type, :source_id, :title, :content,
                     CAST(:metadata AS jsonb), CAST(:embedding AS vector))
                ON CONFLICT (collection, doc_key) DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    source_type = EXCLUDED.source_type,
                    source_id = EXCLUDED.source_id,
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    metadata = EXCLUDED.metadata,
                    embedding = EXCLUDED.embedding
                """
            ),
            {
                "collection": collection,
                "doc_key": doc_key,
                "user_id": user_id,
                "source_type": source_type,
                "source_id": source_id,
                "title": title,
                "content": content,
                "metadata": json.dumps(metadata or {}, ensure_ascii=False),
                "embedding": _vec_literal(embedding),
            },
        )


async def search(
    collection: str,
    user_id: int,
    embedding: list[float],
    *,
    limit: int = 10,
    source_types: list[str] | None = None,
) -> list[dict]:
    await ensure_vector_schema()
    sql = (
        "SELECT doc_key, source_type, source_id, title, content, metadata, "
        "1 - (embedding <=> CAST(:embedding AS vector)) AS score "
        "FROM embeddings WHERE collection = :collection AND user_id = :user_id"
    )
    params: dict = {
        "collection": collection,
        "user_id": user_id,
        "embedding": _vec_literal(embedding),
        "limit": limit,
    }
    if source_types:
        sql += " AND source_type IN :source_types"
    sql += " ORDER BY embedding <=> CAST(:embedding AS vector) LIMIT :limit"

    stmt = text(sql)
    if source_types:
        stmt = stmt.bindparams(bindparam("source_types", expanding=True))
        params["source_types"] = source_types

    async with engine.begin() as conn:
        result = await conn.execute(stmt, params)
        rows = result.mappings().all()

    out = []
    for r in rows:
        meta = r["metadata"]
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        out.append({
            "doc_key": r["doc_key"],
            "source_type": r["source_type"],
            "source_id": r["source_id"],
            "title": r["title"],
            "content": r["content"],
            "metadata": meta or {},
            "score": round(float(r["score"]), 4),
        })
    return out


async def delete(collection: str, doc_key: str) -> None:
    await ensure_vector_schema()
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM embeddings WHERE collection = :collection AND doc_key = :doc_key"),
            {"collection": collection, "doc_key": doc_key},
        )
