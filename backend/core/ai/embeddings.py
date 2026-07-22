from openai import AsyncOpenAI
from core.config.settings import settings

_embedding_client: AsyncOpenAI | None = None


def get_embedding_client() -> AsyncOpenAI | None:
    global _embedding_client
    if _embedding_client is None:
        key = settings.embedding_api_key or settings.llm_api_key
        base = settings.embedding_base_url
        if key:
            _embedding_client = AsyncOpenAI(api_key=key, base_url=base)
    return _embedding_client


async def generate_embedding(text: str, model: str | None = None) -> list[float] | None:
    client = get_embedding_client()
    if not client:
        return None

    text = text[:8000]
    if not text.strip():
        return None

    model = model or settings.embedding_model
    try:
        resp = await client.embeddings.create(model=model, input=text)
        return resp.data[0].embedding
    except Exception:
        return None


async def generate_embedding_batch(texts: list[str], model: str = "text-embedding-3-small") -> list[list[float] | None]:
    client = get_embedding_client()
    if not client:
        return [None] * len(texts)

    texts = [t[:4000] for t in texts]
    try:
        resp = await client.embeddings.create(model=model, input=texts)
        results: list[list[float] | None] = [None] * len(texts)
        for data in resp.data:
            results[data.index] = data.embedding
        return results
    except Exception:
        return [None] * len(texts)
