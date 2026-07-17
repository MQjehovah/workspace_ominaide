from qdrant_client import QdrantClient
from qdrant_client.models import (
    PointStruct, VectorParams, Distance,
    Filter, FieldCondition, MatchValue,
)
from core.config.settings import settings

COLLECTION_NAME = "file_embeddings"
VECTOR_SIZE = 1536

_client: QdrantClient | None = None


def get_qdrant() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=settings.qdrant_url)
        _ensure_collection()
    return _client


def _ensure_collection():
    collections = _client.get_collections().collections
    if not any(c.name == COLLECTION_NAME for c in collections):
        _client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


async def index_file(
    file_id: int,
    user_id: int,
    filename: str,
    content: str,
    workspace_id: int | None = None,
    file_size: int = 0,
):
    from core.ai.embeddings import generate_embedding

    vector = await generate_embedding(content)
    if vector is None:
        return False

    client = get_qdrant()
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            PointStruct(
                id=file_id,
                vector=vector,
                payload={
                    "user_id": user_id,
                    "file_id": file_id,
                    "filename": filename,
                    "workspace_id": workspace_id,
                    "file_size": file_size,
                    "indexed_at": __import__("datetime").datetime.now().isoformat(),
                },
            )
        ],
    )
    return True


async def search_similar(
    user_id: int,
    query: str,
    limit: int = 10,
    workspace_id: int | None = None,
) -> list[dict]:
    from core.ai.embeddings import generate_embedding

    vector = await generate_embedding(query)
    if vector is None:
        return []

    client = get_qdrant()

    must_conditions = [FieldCondition(key="user_id", match=MatchValue(value=user_id))]
    if workspace_id:
        must_conditions.append(
            FieldCondition(key="workspace_id", match=MatchValue(value=workspace_id))
        )

    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=vector,
        query_filter=Filter(must=must_conditions),
        limit=limit,
    )

    return [
        {
            "file_id": r.payload.get("file_id"),
            "filename": r.payload.get("filename"),
            "workspace_id": r.payload.get("workspace_id"),
            "file_size": r.payload.get("file_size"),
            "score": round(r.score, 4),
        }
        for r in results
    ]


async def delete_file_index(file_id: int):
    client = get_qdrant()
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=[file_id],
    )
