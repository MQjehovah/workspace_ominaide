from core.config.settings import settings

_initialized = False


async def _ensure_collection():
    global _initialized
    if _initialized:
        return
    from qdrant_client import QdrantClient
    host = settings.qdrant_url.replace("http://", "").split(":")[0]
    port = int(settings.qdrant_url.split(":")[-1])
    client = QdrantClient(host=host, port=port)
    collections = client.get_collections().collections
    if not any(c.name == "omnidocs" for c in collections):
        from qdrant_client.http import models
        client.create_collection(
            collection_name="omnidocs",
            vectors_config=models.VectorParams(size=1536, distance=models.Distance.COSINE),
        )
    _initialized = True


async def index_content(
    user_id: int,
    source_type: str,
    source_id: int,
    title: str,
    content: str,
    metadata: dict = None,
) -> bool:
    if not settings.data_layer_enabled:
        return False
    try:
        await _ensure_collection()
        from core.ai.embeddings import generate_embedding
        from qdrant_client import QdrantClient
        from qdrant_client.http import models
        from datetime import datetime

        vector = await generate_embedding(content[:8000])
        if vector is None:
            return False
        host = settings.qdrant_url.replace("http://", "").split(":")[0]
        port = int(settings.qdrant_url.split(":")[-1])
        client = QdrantClient(host=host, port=port)
        point_id = f"{source_type}_{source_id}_{user_id}"
        client.upsert(
            collection_name="omnidocs",
            points=[models.PointStruct(
                id=hash(point_id) % (2 ** 63),
                vector=vector,
                payload={
                    "user_id": user_id,
                    "source_type": source_type,
                    "source_id": source_id,
                    "title": title,
                    "content": content[:500],
                    "metadata": metadata or {},
                    "created_at": datetime.utcnow().isoformat(),
                },
            )],
        )
        return True
    except Exception as e:
        print(f"[indexer] error: {e}")
        return False
