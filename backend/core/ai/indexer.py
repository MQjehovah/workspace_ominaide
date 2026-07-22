import json
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
        size = getattr(settings, 'embedding_dimensions', 1024)
        client.create_collection(
            collection_name="omnidocs",
            vectors_config=models.VectorParams(size=size, distance=models.Distance.COSINE),
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


async def extract_and_store_entities(user_id: int, content: str, source_type: str, source_id: int, title: str):
    """Extract entities from content using LLM and store in Qdrant entities collection."""
    if not settings.memory_layer_enabled:
        return

    if not content and not title:
        return

    text = (title + "\n" + (content or ""))[:3000]

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )

        resp = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": "从文本中提取实体（人物、项目、术语），以JSON格式返回数组：[{\"name\":\"实体名\",\"type\":\"person|project|term\"}]。只返回JSON，不要其他文字。"},
                {"role": "user", "content": text},
            ],
            temperature=0.1,
        )

        raw = resp.choices[0].message.content or "[]"
        raw = raw.strip().removeprefix("```json").removesuffix("```").strip()
        entities = json.loads(raw)

        if not entities or not isinstance(entities, list):
            return

        from qdrant_client import QdrantClient
        from qdrant_client.http import models
        from datetime import datetime

        host = settings.qdrant_url.replace("http://", "").split(":")[0]
        port = int(settings.qdrant_url.split(":")[-1])
        qdrant = QdrantClient(host=host, port=port)

        collections = qdrant.get_collections().collections
        if not any(c.name == "entities" for c in collections):
            size = getattr(settings, 'embedding_dimensions', 1024)
            qdrant.create_collection("entities", vectors_config=models.VectorParams(size=size, distance=models.Distance.COSINE))

        from core.ai.embeddings import generate_embedding

        for ent in entities:
            name = ent.get("name", "").strip()
            etype = ent.get("type", "term")
            if not name:
                continue

            vector = await generate_embedding(name)
            if not vector:
                continue

            point_id = f"ent_{name}_{user_id}"
            qdrant.upsert("entities", points=[models.PointStruct(
                id=hash(point_id) % (2 ** 63),
                vector=vector,
                payload={
                    "name": name,
                    "type": etype,
                    "user_id": user_id,
                    "sources": [{"type": source_type, "id": source_id, "title": title}],
                    "first_seen": datetime.utcnow().isoformat(),
                    "last_seen": datetime.utcnow().isoformat(),
                },
            )])
    except Exception as e:
        print(f"[entity] error: {e}")
