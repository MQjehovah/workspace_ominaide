from fastapi import APIRouter, Depends
from pydantic import BaseModel
from core.auth.dependencies import get_current_user
from core.config.settings import settings

router = APIRouter(prefix="/api", tags=["search"])


class SearchRequest(BaseModel):
    q: str
    types: list[str] | None = None
    top_k: int = 10


class SearchResult(BaseModel):
    type: str
    title: str
    snippet: str
    score: float
    source_id: int | None = None
    link: str | None = None


class SearchResponse(BaseModel):
    results: list[SearchResult]


@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest, user: dict = Depends(get_current_user)):
    if not settings.data_layer_enabled:
        return SearchResponse(results=[])
    try:
        from core.ai.embeddings import generate_embedding
        from qdrant_client import QdrantClient

        host = settings.qdrant_url.replace("http://", "").split(":")[0]
        port = int(settings.qdrant_url.split(":")[-1])
        client = QdrantClient(host=host, port=port)
        vector = await generate_embedding(req.q)
        if vector is None:
            return SearchResponse(results=[])

        filter_cond = {"must": [{"key": "user_id", "match": {"value": user["id"]}}]}
        if req.types:
            filter_cond["must"].append({"key": "source_type", "match": {"value": req.types}})

        results = client.search(
            collection_name="omnidocs",
            query_vector=vector,
            limit=req.top_k,
            query_filter=filter_cond,
        )

        items = []
        for r in results:
            p = r.payload
            items.append(SearchResult(
                type=p.get("source_type", "unknown"),
                title=p.get("title", ""),
                snippet=p.get("content", "")[:200],
                score=r.score,
                source_id=p.get("source_id"),
                link=f"/{p.get('source_type', '')}/{p.get('source_id', '')}",
            ))
        return SearchResponse(results=items)
    except Exception as e:
        print(f"[search] error: {e}")
        return SearchResponse(results=[])
