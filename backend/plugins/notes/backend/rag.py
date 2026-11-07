"""Notes RAG: structure-aware chunking, hybrid retrieval and cited Q&A.

This is a portable port of the enterprise Notes-RAG pipeline, adapted to
OmniAide's stack:

- one note -> many evidence chunks (``plugin_note_chunks``)
- BM25 keyword index (``plugin_note_terms``) with a dependency-free
  Chinese bigram tokenizer
- vector recall over JSON embeddings (works on MySQL / PostgreSQL / SQLite)
- RRF fusion + MMR diversity rerank
- cited answer generation over the user's own notes

No external services beyond the configured embedding/LLM endpoints are
required, and every stage degrades gracefully (keyword-only when embeddings
are unavailable).
"""

from __future__ import annotations

from core.logging import get_logger
log = get_logger(__name__)

import asyncio
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config.settings import settings
from core.database.session import async_session
from plugins.notes.backend.content_text import note_content_to_text
from plugins.notes.backend.models import NoteChunk, NoteTerm, PluginNote

# ---------------------------------------------------------------------------
# tokenizer / splitter
# ---------------------------------------------------------------------------

_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_WORD_RE = re.compile(r"[a-z][a-z0-9_+#.-]{2,}")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE_RE = re.compile(r"```[\s\S]*?```")
_URL_RE = re.compile(r"https?://\S+")

_STOP = {
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
    "her", "was", "one", "our", "out", "has", "have", "from", "been",
    "some", "them", "than", "its", "over", "such", "that", "with", "will",
    "this", "each", "make", "like", "into", "many", "then", "they",
    "what", "about", "which", "their", "would", "there", "could", "other",
    "after", "first", "well", "also", "back", "class", "void", "public",
    "static", "return", "final", "import", "null", "true", "false",
    "self", "def", "func", "var", "let", "const", "log", "data", "result",
    "content", "type", "text", "value", "name", "item", "list", "map",
    "http", "https", "www", "com", "org", "png", "jpg", "svg", "img",
    "src", "href", "div", "span", "class", "style",
    "的", "了", "是", "在", "和", "与", "及", "或", "等", "以及", "我",
    "你", "他", "她", "它", "我们", "你们", "他们", "这", "那", "有",
    "就", "不", "也", "都", "要", "会", "着", "被", "把", "对", "为",
    "从", "到", "而", "并", "但", "如果", "因为", "所以", "可以", "一个",
}


def tokenize(text: str) -> list[str]:
    """Dependency-free tokenizer: English words + Chinese bigrams.

    Bigrams give usable BM25 recall for Chinese without pulling in jieba while
    keeping the index small enough for personal-scale note collections.
    """
    if not text:
        return []
    text = _FENCE_RE.sub(" ", text)
    text = _URL_RE.sub(" ", text)
    tokens: list[str] = []
    for m in _WORD_RE.finditer(text.lower()):
        w = m.group(0)
        if w not in _STOP:
            tokens.append(w)
    for m in _CJK_RE.finditer(text):
        run = m.group(0)
        if len(run) == 1:
            continue
        for i in range(len(run) - 1):
            bg = run[i:i + 2]
            if bg not in _STOP:
                tokens.append(bg)
        if len(run) <= 4 and run not in _STOP:
            tokens.append(run)
    return tokens


def _split_long(text: str, size: int, overlap: int) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    size = max(120, int(size))
    overlap = max(0, min(int(overlap), size // 2))
    if len(text) <= size:
        return [text]

    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            window = text[start:end]
            cut = max(
                window.rfind("\n"),
                window.rfind("。"), window.rfind("！"), window.rfind("？"),
                window.rfind("；"), window.rfind(". "),
            )
            if cut > size * 0.55:
                end = start + cut + 1
        piece = text[start:end].strip()
        if piece:
            parts.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return parts


def split_structured(content: str, title: str = "") -> list[dict[str, str]]:
    """Split markdown-ish note text by headings, then by length.

    Each chunk carries a ``context`` chain (note title > h1 > h2 ...) which is
    also prepended to the embedding input (contextual retrieval).
    """
    text = note_content_to_text(content or "").strip()
    if not text:
        return []

    size = int(getattr(settings, "notes_chunk_size", 600) or 600)
    overlap = int(getattr(settings, "notes_chunk_overlap", 80) or 80)

    lines = text.splitlines()
    sections: list[tuple[list[str], str]] = []
    chain: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        body = "\n".join(buf).strip()
        if body:
            sections.append((list(chain), body))
        buf.clear()

    for line in lines:
        m = _HEADING_RE.match(line.strip())
        if m:
            flush()
            level = len(m.group(1))
            heading = m.group(2).strip()
            chain = chain[: level - 1] + [heading]
        else:
            buf.append(line)
    flush()

    if not sections:
        sections = [([], text)]

    chunks: list[dict[str, str]] = []
    for chain_items, body in sections:
        ctx = " > ".join(chain_items)
        if title:
            ctx = f"{title} > {ctx}" if ctx else title
        for piece in _split_long(body, size, overlap):
            chunks.append({"content": piece, "context": ctx})
    return chunks


# ---------------------------------------------------------------------------
# indexing
# ---------------------------------------------------------------------------

def _emb_json(vec: list[float] | None) -> str | None:
    return json.dumps(vec) if vec else None


def _parse_emb(raw: str | None) -> list[float] | None:
    if not raw:
        return None
    try:
        v = json.loads(raw)
    except Exception:
        return None
    if not isinstance(v, list) or not v:
        return None
    try:
        return [float(x) for x in v]
    except Exception:
        return None


_index_lock = asyncio.Lock()


async def index_note_rag(
    user_id: int,
    note_id: int,
    title: str,
    content: str | None,
    *,
    db: AsyncSession | None = None,
) -> dict[str, int]:
    """Serialize reindexing so two saves of the same note cannot collide."""
    async with _index_lock:
        return await _index_note_rag_locked(user_id, note_id, title, content, db=db)


async def _index_note_rag_locked(
    user_id: int,
    note_id: int,
    title: str,
    content: str | None,
    *,
    db: AsyncSession | None = None,
) -> dict[str, int]:
    """Rebuild chunks + terms for one note. Safe to call on every save."""
    if not getattr(settings, "notes_rag_enabled", True):
        return {"chunks": 0, "terms": 0, "embedded": 0}

    own_session = db is None
    if own_session:
        db = async_session()
    try:
        await db.execute(delete(NoteChunk).where(NoteChunk.note_id == note_id))
        await db.execute(delete(NoteTerm).where(NoteTerm.note_id == note_id))

        chunks = split_structured(content or "", title or "")
        terms = Counter(tokenize((title or "") + "\n" + note_content_to_text(content or "")))
        if terms:
            db.add_all([
                NoteTerm(note_id=note_id, user_id=user_id, term=t[:120], tf=n)
                for t, n in terms.items()
            ])

        embedded = 0
        if chunks:
            embeddings: list[list[float] | None] = []
            try:
                from core.ai.embeddings import generate_embedding_batch
                inputs = [
                    (c["context"] + "\n\n" + c["content"]).strip()
                    for c in chunks
                ]
                embeddings = await generate_embedding_batch(
                    inputs, model=settings.embedding_model
                )
            except Exception as e:
                log.warning(f"[notes.rag] embedding error note={note_id}: {e}")
                embeddings = []

            for i, c in enumerate(chunks):
                emb = embeddings[i] if i < len(embeddings) else None
                if emb:
                    embedded += 1
                db.add(NoteChunk(
                    note_id=note_id,
                    user_id=user_id,
                    chunk_index=i,
                    content=c["content"],
                    context=c["context"][:1000],
                    embedding=_emb_json(emb),
                ))

        if own_session:
            await db.commit()
        else:
            await db.flush()
        return {"chunks": len(chunks), "terms": len(terms), "embedded": embedded}
    except Exception as e:
        log.warning(f"[notes.rag] index error note={note_id}: {e}")
        if own_session:
            await db.rollback()
        return {"chunks": 0, "terms": 0, "embedded": 0}
    finally:
        if own_session:
            await db.close()


async def delete_note_rag(db: AsyncSession, note_ids: list[int]) -> None:
    if not note_ids:
        return
    for i in range(0, len(note_ids), 500):
        part = note_ids[i:i + 500]
        await db.execute(delete(NoteChunk).where(NoteChunk.note_id.in_(part)))
        await db.execute(delete(NoteTerm).where(NoteTerm.note_id.in_(part)))


async def reindex_all(user_id: int, limit: int = 200) -> dict[str, int]:
    """Backfill the RAG index for a user's existing notes."""
    stats = {"notes": 0, "chunks": 0, "terms": 0, "embedded": 0}
    async with async_session() as db:
        rows = await db.execute(
            select(PluginNote)
            .where(PluginNote.user_id == user_id, PluginNote.is_folder == 0)
            .order_by(PluginNote.updated_at.desc())
            .limit(max(1, limit))
        )
        notes = list(rows.scalars().all())
        for n in notes:
            r = await index_note_rag(n.user_id, n.id, n.title, n.content, db=db)
            await db.commit()
            stats["notes"] += 1
            stats["chunks"] += r["chunks"]
            stats["terms"] += r["terms"]
            stats["embedded"] += r["embedded"]
    return stats


async def ensure_indexed(user_id: int, limit: int = 500) -> dict[str, int]:
    """Lazy one-time backfill so existing notes work before the first save.

    Returns the reindex stats (empty when the index already has chunks).
    """
    async with async_session() as db:
        notes = (await db.execute(
            select(func.count(PluginNote.id)).where(
                PluginNote.user_id == user_id, PluginNote.is_folder == 0
            )
        )).scalar() or 0
        chunks = (await db.execute(
            select(func.count(NoteChunk.id)).where(NoteChunk.user_id == user_id)
        )).scalar() or 0
    if notes and not chunks:
        return await reindex_all(user_id, limit=limit)
    return {}


async def rag_status(user_id: int) -> dict[str, int]:
    async with async_session() as db:
        note_count = (await db.execute(
            select(func.count(PluginNote.id)).where(
                PluginNote.user_id == user_id, PluginNote.is_folder == 0
            )
        )).scalar() or 0
        chunk_count = (await db.execute(
            select(func.count(NoteChunk.id)).where(NoteChunk.user_id == user_id)
        )).scalar() or 0
        term_count = (await db.execute(
            select(func.count(NoteTerm.id)).where(NoteTerm.user_id == user_id)
        )).scalar() or 0
        embedded = (await db.execute(
            select(func.count(NoteChunk.id)).where(
                NoteChunk.user_id == user_id, NoteChunk.embedding.isnot(None)
            )
        )).scalar() or 0
    return {
        "notes": int(note_count),
        "chunks": int(chunk_count),
        "terms": int(term_count),
        "embedded_chunks": int(embedded),
    }


# ---------------------------------------------------------------------------
# recall
# ---------------------------------------------------------------------------

def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return -1.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


async def vector_recall(
    db: AsyncSession, user_id: int, query_vec: list[float], top_k: int
) -> list[dict[str, Any]]:
    if not query_vec:
        return []
    rows = await db.execute(
        select(
            NoteChunk.note_id, NoteChunk.chunk_index, NoteChunk.content,
            NoteChunk.context, NoteChunk.embedding,
        ).where(NoteChunk.user_id == user_id)
    )
    best: dict[int, dict[str, Any]] = {}
    for note_id, idx, content, context, raw in rows.all():
        vec = _parse_emb(raw)
        if not vec:
            continue
        score = _cosine(query_vec, vec)
        if score < 0:
            continue
        cur = best.get(note_id)
        if cur is None or score > cur["score"]:
            best[note_id] = {
                "note_id": note_id,
                "score": score,
                "chunk_index": idx or 0,
                "content": content or "",
                "context": context or "",
                "embedding": vec,
            }
    ranked = sorted(best.values(), key=lambda x: x["score"], reverse=True)
    return ranked[:max(1, top_k)]


async def bm25_recall(
    db: AsyncSession, user_id: int, query: str, top_k: int
) -> list[dict[str, Any]]:
    terms = sorted(set(tokenize(query)))
    if not terms:
        return []

    note_ids = [r[0] for r in (await db.execute(
        select(PluginNote.id).where(
            PluginNote.user_id == user_id, PluginNote.is_folder == 0
        )
    )).all()]
    if not note_ids:
        return []
    n_docs = len(note_ids)

    dl_map: dict[int, int] = {}
    for i in range(0, len(note_ids), 500):
        part = note_ids[i:i + 500]
        rows = await db.execute(
            select(NoteTerm.note_id, func.sum(NoteTerm.tf))
            .where(NoteTerm.user_id == user_id, NoteTerm.note_id.in_(part))
            .group_by(NoteTerm.note_id)
        )
        for nid, tf in rows.all():
            dl_map[int(nid)] = int(tf or 0)
    avgdl = (sum(dl_map.values()) / n_docs) if dl_map else 0.0
    if avgdl <= 0:
        return []

    postings: list[tuple[int, str, int]] = []
    for i in range(0, len(terms), 200):
        part = terms[i:i + 200]
        rows = await db.execute(
            select(NoteTerm.note_id, NoteTerm.term, NoteTerm.tf).where(
                NoteTerm.user_id == user_id, NoteTerm.term.in_(part)
            )
        )
        for nid, term, tf in rows.all():
            postings.append((int(nid), term, int(tf or 0)))
    if not postings:
        return []

    df_counter: dict[str, set[int]] = defaultdict(set)
    for nid, term, _tf in postings:
        df_counter[term].add(nid)

    k1, b = 1.5, 0.75
    scores: dict[int, float] = defaultdict(float)
    for nid, term, tf in postings:
        df = len(df_counter[term])
        idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
        dl = dl_map.get(nid, 0)
        denom = tf + k1 * (1.0 - b + b * dl / avgdl)
        scores[nid] += idf * (tf * (k1 + 1.0)) / denom

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [{"note_id": nid, "score": float(s)} for nid, s in ranked[:max(1, top_k)]]


# ---------------------------------------------------------------------------
# hybrid search
# ---------------------------------------------------------------------------

def _rrf(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    scores: dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, nid in enumerate(ranking):
            scores[nid] += 1.0 / (k + rank + 1)
    return dict(scores)


_COMPLEX_MARKERS = (
    "和", "与", "以及", "或", "还是", "怎么", "如何", "为什么",
    "区别", "对比", "哪些", "什么", "分别", "总结", "所有", "包括",
)


def _needs_rewrite(query: str) -> bool:
    """Skip the rewrite LLM call for short, simple questions."""
    q = (query or "").strip()
    if not q:
        return False
    if len(q) >= 30:
        return True
    return len(q) >= int(getattr(settings, "notes_rag_query_rewrite_min_len", 20) or 20) \
        and any(m in q for m in _COMPLEX_MARKERS)


async def _rewrite_queries(query: str) -> list[str]:
    """Cheap query expansion for longer questions; never blocks retrieval."""
    if not settings.llm_api_key or not _needs_rewrite(query):
        return []
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        resp = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": (
                    "你是知识库检索助手。把用户问题改写成最多 2 个不同角度的中文子问题，"
                    "只返回 JSON：{\"queries\":[\"子问题1\",\"子问题2\"]}"
                )},
                {"role": "user", "content": query},
            ],
            temperature=0.1,
        )
        raw = (resp.choices[0].message.content or "").strip()
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return []
        data = json.loads(m.group(0))
        return [q.strip() for q in (data.get("queries") or []) if isinstance(q, str) and q.strip()][:2]
    except Exception:
        return []


def _mmr_rank(
    note_ids: list[int],
    rel: dict[int, float],
    embeddings: dict[int, list[float]],
    *,
    top_k: int,
    lam: float,
) -> list[int]:
    selected: list[int] = []
    remaining = list(note_ids)
    while remaining and len(selected) < top_k:
        best_id = None
        best_val = float("-inf")
        for nid in remaining:
            sim = 0.0
            for sid in selected:
                s = _cosine(embeddings.get(nid, []), embeddings.get(sid, []))
                if s > sim:
                    sim = s
            val = lam * rel.get(nid, 0.0) - (1.0 - lam) * sim
            if val > best_val:
                best_val = val
                best_id = nid
        if best_id is None:
            break
        selected.append(best_id)
        remaining.remove(best_id)
    return selected


async def hybrid_search(
    db: AsyncSession,
    user_id: int,
    query: str,
    *,
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """Vector + BM25 + RRF + MMR over the user's notes."""
    query = (query or "").strip()
    if not query:
        return []
    top_k = int(top_k or getattr(settings, "notes_rag_top_k", 8) or 8)
    recall_k = int(getattr(settings, "notes_rag_recall_k", 30) or 30)

    queries = [query] + await _rewrite_queries(query)
    vector_rankings: list[list[int]] = []
    bm_rankings: list[list[int]] = []
    chunk_map: dict[int, dict[str, Any]] = {}
    emb_map: dict[int, list[float]] = {}

    from core.ai.embeddings import generate_embedding

    for q in queries:
        vec = await generate_embedding(q)
        if vec:
            hits = await vector_recall(db, user_id, vec, recall_k)
            vector_rankings.append([h["note_id"] for h in hits])
            for h in hits:
                cur = chunk_map.get(h["note_id"])
                if cur is None or h["score"] > cur["score"]:
                    chunk_map[h["note_id"]] = h
                emb_map[h["note_id"]] = h.get("embedding") or []
        bm = await bm25_recall(db, user_id, q, recall_k)
        if bm:
            bm_rankings.append([h["note_id"] for h in bm])
            for h in bm:
                chunk_map.setdefault(h["note_id"], {
                    "note_id": h["note_id"], "score": 0.0,
                    "chunk_index": 0, "content": "", "context": "",
                })

    rrf = _rrf(vector_rankings + bm_rankings)
    if not rrf:
        return []

    vector_set = {nid for r in vector_rankings for nid in r}
    bm_set = {nid for r in bm_rankings for nid in r}
    sources: dict[int, set[str]] = defaultdict(set)
    for nid in rrf:
        if nid in vector_set:
            sources[nid].add("vector")
        if nid in bm_set:
            sources[nid].add("keyword")

    candidate_ids = sorted(rrf, key=rrf.get, reverse=True)[: max(recall_k, top_k * 3)]
    rows = await db.execute(
        select(PluginNote).where(
            PluginNote.user_id == user_id,
            PluginNote.id.in_(candidate_ids),
            PluginNote.is_folder == 0,
        )
    )
    notes = {n.id: n for n in rows.scalars().all()}
    if not notes:
        return []

    # Fill best-chunk text for BM25-only candidates.
    missing = [nid for nid in notes if not chunk_map.get(nid, {}).get("content")]
    if missing:
        rows = await db.execute(
            select(
                NoteChunk.note_id, NoteChunk.chunk_index, NoteChunk.content,
                NoteChunk.context, NoteChunk.embedding,
            ).where(NoteChunk.note_id.in_(missing)).order_by(
                NoteChunk.note_id, NoteChunk.chunk_index
            )
        )
        for nid, idx, content, context, raw in rows.all():
            cur = chunk_map.setdefault(nid, {})
            if not cur.get("content"):
                cur.update({
                    "note_id": nid, "score": 0.0, "chunk_index": idx or 0,
                    "content": content or "", "context": context or "",
                })
            emb = _parse_emb(raw)
            if emb and nid not in emb_map:
                emb_map[nid] = emb

    max_rrf = max(rrf.values()) or 1.0
    rel = {nid: rrf.get(nid, 0.0) / max_rrf for nid in notes}
    ordered = sorted(rel, key=rel.get, reverse=True)

    slots = min(top_k, len(ordered))
    if len(ordered) > 1 and getattr(settings, "notes_rag_enabled", True):
        ordered = _mmr_rank(
            ordered, rel, emb_map,
            top_k=slots,
            lam=float(getattr(settings, "notes_rag_mmr_lambda", 0.7) or 0.7),
        )
    else:
        ordered = ordered[:slots]

    results: list[dict[str, Any]] = []
    for nid in ordered:
        n = notes.get(nid)
        if not n:
            continue
        c = chunk_map.get(nid) or {}
        body = c.get("content") or note_content_to_text(n.content or "")
        snippet = " ".join((body or "").split())[:260]
        results.append({
            "note_id": nid,
            "id": nid,
            "title": n.title or "无标题",
            "snippet": snippet,
            "content": (body or "")[:1200],
            "context": c.get("context") or "",
            "chunk_index": c.get("chunk_index") or 0,
            "chunks": [{
                "chunk_index": c.get("chunk_index") or 0,
                "content": (body or "")[:2000],
                "context": c.get("context") or "",
            }],
            "score": round(float(rel.get(nid, 0.0)), 4),
            "sources": sorted(sources.get(nid, set())),
            "updated_at": n.updated_at.isoformat() if n.updated_at else None,
            "link": f"/notes/{nid}",
        })
    return results


async def _judge_sufficiency(question: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    """Ask the LLM whether the retrieved evidence is enough to answer."""
    if not results:
        return {"sufficient": False, "followup_query": question}
    parts = []
    for i, r in enumerate(results[:8], 1):
        text = (r.get("content") or r.get("snippet") or "")[:500]
        parts.append(f"[{i}] 《{r.get('title') or ''}》\n{text}")
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        resp = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": (
                    "你是知识库检索评估器。判断给出的笔记片段是否足以回答用户问题。\n"
                    "如果足够，返回 {\"sufficient\": true}；如果不足，返回 "
                    "{\"sufficient\": false, \"followup_query\": \"一个用于补充检索的中文问题\"}。\n"
                    "只返回 JSON，不要其他内容。"
                )},
                {"role": "user", "content": f"问题：{question}\n\n片段：\n" + "\n\n".join(parts)},
            ],
            temperature=0.0,
        )
        raw = (resp.choices[0].message.content or "").strip()
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return {"sufficient": True}
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else {"sufficient": True}
    except Exception as e:
        log.warning(f"[notes.rag] sufficiency judge error: {e}")
        return {"sufficient": True}


async def _retrieve_agentic(
    db: AsyncSession, user_id: int, question: str, *, top_k: int | None = None
) -> list[dict[str, Any]]:
    """Retrieve, judge sufficiency, then run follow-up searches (agentic RAG)."""
    hops = 1
    if getattr(settings, "notes_rag_agentic_enabled", True):
        hops = max(1, int(getattr(settings, "notes_rag_agentic_hops", 2) or 2))
    if not settings.llm_api_key:
        hops = 1

    merged: list[dict[str, Any]] = []
    seen: set[int] = set()
    query = question
    for hop in range(hops):
        more = await hybrid_search(db, user_id, query, top_k=top_k)
        for item in more:
            nid = item.get("note_id")
            if nid not in seen:
                seen.add(nid)
                merged.append(item)
        if hop >= hops - 1:
            break
        decision = await _judge_sufficiency(question, merged)
        if decision.get("sufficient") is True:
            break
        followup = str(decision.get("followup_query") or "").strip()
        if not followup or followup == query:
            break
        query = followup

    limit = int(top_k or getattr(settings, "notes_rag_top_k", 8) or 8)
    return merged[:max(limit, 1)]


async def ask_notes(
    db: AsyncSession,
    user_id: int,
    question: str,
    *,
    top_k: int | None = None,
) -> dict[str, Any]:
    """Cited RAG answer grounded strictly in the user's notes."""
    results = await _retrieve_agentic(db, user_id, question, top_k=top_k)
    if not results:
        return {
            "answer": "你的笔记里没有找到与这个问题相关的内容。",
            "sources": [],
        }
    if not settings.llm_api_key:
        raise RuntimeError("LLM API key not configured")

    blocks = []
    for i, r in enumerate(results, 1):
        ctx = f"（{r['context']}）\n" if r.get("context") else ""
        body = r.get("content") or r.get("snippet") or ""
        blocks.append(
            f"[{i}] 《{r['title']}》\n{ctx}{body}"
        )
    context = "\n\n".join(blocks)

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    resp = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": (
                "你是用户的私人知识库助手。只能依据下面提供的笔记片段回答，"
                "不要编造片段之外的信息。回答要简洁、有条理；"
                "引用来源时使用 [1][2] 这样的编号，并在末尾列出参考笔记。"
                "如果片段不足以回答，明确说“笔记里没有找到足够的信息”。"
            )},
            {"role": "user", "content": f"笔记片段：\n{context}\n\n问题：{question}"},
        ],
        temperature=0.2,
    )
    answer = (resp.choices[0].message.content or "").strip()
    return {
        "answer": answer,
        "sources": [
            {
                "index": i,
                "note_id": r["note_id"],
                "title": r["title"],
                "snippet": r["snippet"],
                "content": r.get("content") or "",
                "context": r.get("context") or "",
                "chunk_index": r.get("chunk_index") or 0,
                "chunks": r.get("chunks") or [],
                "score": r["score"],
                "link": r["link"],
            }
            for i, r in enumerate(results, 1)
        ],
    }


async def similar_notes(
    db: AsyncSession, user_id: int, note_id: int, *, top_k: int = 5
) -> list[dict[str, Any]]:
    row = await db.execute(
        select(NoteChunk.embedding).where(
            NoteChunk.note_id == note_id, NoteChunk.embedding.isnot(None)
        ).order_by(NoteChunk.chunk_index).limit(1)
    )
    raw = row.scalar_one_or_none()
    vec = _parse_emb(raw)
    if not vec:
        return []
    hits = await vector_recall(db, user_id, vec, top_k + 1)
    hits = [h for h in hits if h["note_id"] != note_id][:top_k]
    if not hits:
        return []
    ids = [h["note_id"] for h in hits]
    rows = await db.execute(select(PluginNote).where(PluginNote.id.in_(ids)))
    notes = {n.id: n for n in rows.scalars().all()}
    out = []
    for h in hits:
        n = notes.get(h["note_id"])
        if not n:
            continue
        out.append({
            "note_id": n.id,
            "title": n.title or "无标题",
            "snippet": " ".join((h.get("content") or "").split())[:200],
            "score": round(float(h["score"]), 4),
            "link": f"/notes/{n.id}",
        })
    return out
