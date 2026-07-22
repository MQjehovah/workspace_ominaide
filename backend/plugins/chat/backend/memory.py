"""Build user context (profile + entities) for chat system prompt."""
from core.config.settings import settings


async def build_context(user_id: int, query: str = "") -> str | None:
    parts = []
    try:
        from sqlalchemy import select
        from core.auth.domain.models import UserProfile
        from core.database.session import async_session
        async with async_session() as db:
            r = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
            p = r.scalar_one_or_none()
            if p:
                info = []
                if p.name: info.append(f"姓名: {p.name}")
                if p.role: info.append(f"角色: {p.role}")
                if p.company: info.append(f"公司: {p.company}")
                if p.contacts:
                    import json
                    cs = json.loads(p.contacts) if isinstance(p.contacts, str) else p.contacts
                    if cs: info.append("联系人: " + "; ".join([f'{c.get("name","")}({c.get("relation","")})' for c in cs]))
                if p.projects:
                    import json
                    ps = json.loads(p.projects) if isinstance(p.projects, str) else p.projects
                    if ps: info.append("项目: " + "; ".join([f'{p.get("name","")}({p.get("deadline","")})' for p in ps]))
                if info:
                    parts.append("【用户信息】\n" + "\n".join(info))
    except Exception:
        pass

    if settings.memory_layer_enabled:
        try:
            from qdrant_client import QdrantClient
            from core.ai.embeddings import generate_embedding
            host = settings.qdrant_url.replace("http://","").split(":")[0]
            port = int(settings.qdrant_url.split(":")[-1])
            qc = QdrantClient(host=host, port=port)
            if any(c.name == "entities" for c in qc.get_collections().collections):
                vec = await generate_embedding(query)
                if vec:
                    hits = qc.search("entities", query_vector=vec, limit=5, query_filter={"must": [{"key": "user_id", "match": {"value": user_id}}]})
                    if hits:
                        related = [f"{h.payload.get('name','')}({h.payload.get('type','')})" for h in hits]
                        parts.append("【相关实体】\n" + ", ".join(related))
        except Exception:
            pass

    return "\n\n".join(parts) if parts else None
