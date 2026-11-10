
from core.logging import get_logger
log = get_logger(__name__)
from ai.llm.usage import tracked_create
import json
import re
from core.config.settings import settings

DOCS_COLLECTION = "omnidocs"
ENTITIES_COLLECTION = "entities"

# Names the extractor should never turn into graph nodes: API routes, code
# identifiers, operation verbs and test placeholders.
ENTITY_STOPWORDS = {
    "id", "run", "runs", "routine", "routines", "bot", "bots", "mcp",
    "note", "notes", "memory", "memories", "automation", "plugin", "plugins",
    "创建", "修改", "删除", "更新", "查询", "保存", "导入",
    "创建笔记", "修改笔记", "删除笔记", "文件库导入",
}
_INVALID_ENTITY_NAME = re.compile(r"[{}<>/\\|=]|^[A-Za-z]$")
_CANONICAL_TYPES = {
    "person", "project", "term", "product", "organization",
    "location", "event", "topic", "technology", "task", "document",
}


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
        from ai.llm.embeddings import generate_embedding
        from ai.retrieval import vector_store
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
        log.warning(f"[indexer] error: {e}")
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

        resp = await tracked_create(client, 
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": "从文本中提取稳定的实体，以JSON格式返回数组：[{\"name\":\"实体名\",\"type\":\"person|project|term|product|organization|location|event|topic|technology|task|document\"}]。不要提取代码路径、API 路由、操作动词、单个字母或测试占位符。只返回JSON，不要其他文字。"},
                {"role": "user", "content": text_in},
            ],
            temperature=0.1,
        )

        raw = resp.choices[0].message.content or "[]"
        raw = raw.strip().removeprefix("```json").removesuffix("```").strip()
        entities = json.loads(raw)

        if not entities or not isinstance(entities, list):
            return

        from ai.retrieval import vector_store
        from ai.llm.embeddings import generate_embedding
        from datetime import datetime

        canonical_items: list[tuple[str, str]] = []
        for ent in entities:
            name = ent.get("name", "").strip()
            etype = str(ent.get("type", "term")).strip().lower()
            if etype not in _CANONICAL_TYPES:
                etype = "term"
            if not name or len(name) < 2:
                continue
            if name.lower() in ENTITY_STOPWORDS or _INVALID_ENTITY_NAME.search(name):
                continue
            canonical_items.append((name, etype))

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
            if etype == "person":
                try:
                    from ai.memory.people import service as people_service

                    await people_service.mention_person(
                        user_id, name,
                        source_type=source_type,
                        source_id=source_id,
                        title=title,
                    )
                except Exception as exc:
                    log.warning("[entity] people index error: %s", exc)

        if canonical_items:
            from ai.entities.service import add_mention, resolve_entity
            from core.database.session import async_session

            async with async_session() as db:
                for name, etype in canonical_items:
                    entity = await resolve_entity(
                        db, user_id, etype, name,
                        source="event", confidence=0.8,
                    )
                    if entity is None:
                        continue
                    await add_mention(
                        db,
                        user_id,
                        entity.id,
                        source_type=source_type,
                        source_id=source_id,
                        quote=(title or name)[:300],
                        role="mentions",
                        confidence=0.8,
                        extracted_by="llm",
                    )
                await db.commit()
    except Exception as e:
        log.warning(f"[entity] error: {e}")
