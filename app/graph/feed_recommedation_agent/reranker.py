"""
app/graph/feed_recommedation_agent/reranker.py
===============================================
Jina Reranker Module
---------------------
Re-scores a list of candidate documents against a query string using the
Jina reranker API.

Model: jina-reranker-v1-base-en
API:   POST https://api.jina.ai/v1/rerank

Typical usage in the recommendation pipeline:
  1. Vector search in Qdrant → top-N candidates  (N = RERANK_FETCH_K, e.g. 30)
  2. Reranker → re-scores all N candidates
  3. Return top-K after reranking              (K = TOP_K, e.g. 10)

This two-stage approach gives much better precision than vector search alone,
because the reranker uses a cross-encoder (query + document together) rather
than independent embeddings.
"""

import os
import aiohttp
from app.core.logger import get_logger

logger = get_logger(__name__)

JINA_API_KEY      = os.getenv("JINA_API_KEY", "")
RERANKER_MODEL    = os.getenv("RERANKER_MODEL", "jina-reranker-v1-base-en")
JINA_RERANK_URL   = "https://api.jina.ai/v1/rerank"
RERANK_FETCH_K    = int(os.getenv("RERANK_FETCH_K", "30"))


async def rerank(
    query     : str,
    documents : list[str],
    top_n     : int | None = None,
) -> list[dict]:
    """
    Rerank a list of text documents against a query.

    Args:
        query:     The query string (e.g. investor's tags joined as text).
        documents: Candidate document strings to rerank.
        top_n:     How many top results to return. Defaults to len(documents).

    Returns:
        List of dicts sorted by relevance score (highest first):
        [{"index": 2, "score": 0.97}, {"index": 0, "score": 0.85}, ...]
        `index` maps back to the original `documents` list position.

    Raises:
        ValueError: If JINA_API_KEY is not set.
        RuntimeError: On non-200 API response.
    """
    if not JINA_API_KEY:
        raise ValueError("JINA_API_KEY is not set in environment variables.")
    if not documents:
        return []

    headers = {
        "Authorization": f"Bearer {JINA_API_KEY}",
        "Content-Type": "application/json",
    }
    payload: dict = {
        "model"    : RERANKER_MODEL,
        "query"    : query,
        "documents": documents,
    }
    if top_n is not None:
        payload["top_n"] = top_n

    async with aiohttp.ClientSession() as session:
        async with session.post(JINA_RERANK_URL, json=payload, headers=headers) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"Jina Reranker API error {resp.status}: {body}")
            data = await resp.json()

    results = data.get("results", [])
    logger.info(
        "[Reranker] Reranked %d documents → returning top %d (model: %s).",
        len(documents),
        len(results),
        RERANKER_MODEL,
    )
    return results


def build_query_from_tags(tags: list[str]) -> str:
    """
    Convert an investor's tag list into a single query string for the reranker.

    Example: ["fintech", "saas", "b2b"] → "fintech saas b2b"
    """
    return " ".join(tags)


def build_document_from_pitchdeck(hit: dict) -> str:
    """
    Convert a Qdrant search hit's payload into a document string for the reranker.

    Uses the pitchdeck's tags. If you later add a description field to the
    pitchdeck payload, include it here for richer reranking signal.

    Example: {"tags": ["saas", "b2b"], "startup_id": "..."} → "saas b2b"
    """
    tags = hit.get("tags") or []
    return " ".join(tags) if tags else hit.get("pitchdeck_id", "")