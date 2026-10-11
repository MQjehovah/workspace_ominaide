"""File embedding index backed by pgvector (previously Qdrant)."""
from core.ai import vector_store

COLLECTION_NAME = "file_embeddings"


async def index_file(
    file_id: int,
    user_id: int,
    filename: str,
    content: str,
    file_size: int = 0,
):
    from core.ai.embeddings import generate_embedding
    from datetime import datetime

    vector = await generate_embedding(content)
    if vector is None:
        return False

    await vector_store.upsert(
        COLLECTION_NAME,
        doc_key=str(file_id),
        user_id=user_id,
        embedding=vector,
        source_type="file",
        source_id=file_id,
        title=filename,
        content=content[:500],
        metadata={
            "file_id": file_id,
            "filename": filename,
            "file_size": file_size,
            "indexed_at": datetime.now().isoformat(),
        },
    )
    return True


async def search_similar(
    user_id: int,
    query: str,
    limit: int = 10,
) -> list[dict]:
    from core.ai.embeddings import generate_embedding

    vector = await generate_embedding(query)
    if vector is None:
        return []

    hits = await vector_store.search(
        COLLECTION_NAME, user_id, vector, limit=limit
    )
    return [
        {
            "file_id": h["metadata"].get("file_id", h["source_id"]),
            "filename": h["title"],
            "file_size": h["metadata"].get("file_size"),
            "score": h["score"],
        }
        for h in hits
    ]


async def delete_file_index(file_id: int):
    await vector_store.delete(COLLECTION_NAME, str(file_id))
