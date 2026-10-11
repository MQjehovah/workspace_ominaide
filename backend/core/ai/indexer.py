import json
from core.config.settings import settings

DOCS_COLLECTION = "omnidocs"
ENTITIES_COLLECTION = "entities"


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
        from core.ai.embeddings import generate_embedding
        from core.ai import vector_store
        from datetime import datetime

        vector = await generate_embedding(content[:8000])
        if vector is None:
            return False

        doc_key = f"{source_type}_{source_id}_{user_id}"
        await vector_store.upsert(
            DOCS_COLLECTION,
            doc_key=doc_key,
            user_id=user_id,
            embedding=vector,
            source_type=source_type,
            source_id=source_id,
            title=title,
            content=content[:500],
            metadata={**(metadata or {}), "created_at": datetime.utcnow().isoformat()},
        )
        return True
    except Exception as e:
        print(f"[indexer] error: {e}")
        return False


async def extract_and_store_entities(user_id: int, content: str, source_type: str, source_id: int, title: str):
    """Extract entities from content using LLM and store them in pgvector."""
    if not settings.memory_layer_enabled:
        return

    if not content and not title:
        return

    text_in = (title + "\n" + (content or ""))[:3000]

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
                {"role": "user", "content": text_in},
            ],
            temperature=0.1,
        )

        raw = resp.choices[0].message.content or "[]"
        raw = raw.strip().removeprefix("```json").removesuffix("```").strip()
        entities = json.loads(raw)

        if not entities or not isinstance(entities, list):
            return

        from core.ai import vector_store
        from core.ai.embeddings import generate_embedding
        from datetime import datetime

        for ent in entities:
            name = ent.get("name", "").strip()
            etype = ent.get("type", "term")
            if not name:
                continue

            vector = await generate_embedding(name)
            if not vector:
                continue

            doc_key = f"ent_{name}_{user_id}"
            await vector_store.upsert(
                ENTITIES_COLLECTION,
                doc_key=doc_key,
                user_id=user_id,
                embedding=vector,
                source_type="entity",
                source_id=source_id,
                title=name,
                content=name,
                metadata={
                    "name": name,
                    "type": etype,
                    "sources": [{"type": source_type, "id": source_id, "title": title}],
                    "first_seen": datetime.utcnow().isoformat(),
                    "last_seen": datetime.utcnow().isoformat(),
                },
            )
    except Exception as e:
        print(f"[entity] error: {e}")
