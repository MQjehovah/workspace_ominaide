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
        from core.ai import vector_store

        vector = await generate_embedding(req.q)
        if vector is None:
            return SearchResponse(results=[])

        hits = await vector_store.search(
            "omnidocs",
            user["id"],
            vector,
            limit=req.top_k,
            source_types=req.types,
        )

        items = []
        for h in hits:
            items.append(SearchResult(
                type=h.get("source_type") or "unknown",
                title=h.get("title") or "",
                snippet=(h.get("content") or "")[:200],
                score=h.get("score", 0.0),
                source_id=h.get("source_id"),
                link=f"/{h.get('source_type', '')}/{h.get('source_id', '')}",
            ))
        return SearchResponse(results=items)
    except Exception as e:
        print(f"[search] error: {e}")
        return SearchResponse(results=[])
