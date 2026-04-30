"""
app/graph/feed_recommedation_agent/tools/pitchdeck_tools.py
===========================================================
Pitchdeck embedding pipeline + investor → pitchdeck recommendation.

Recommendation pipeline (two-stage):
  Stage 1 — Vector search  : Qdrant ANN fetches top-RERANK_FETCH_K candidates fast
  Stage 2 — Reranker        : Jina cross-encoder re-scores candidates → top-K returned

This gives much better precision than pure vector search.
"""

import os
import uuid
from typing import Optional

from qdrant_client.models import PointStruct

from app.core.qdrant_client import get_qdrant
from app.core.supabase_client import supabase
from app.core.logger import get_logger
from app.graph.feed_recommedation_agent.embedding import aggregate_embeddings
from app.graph.feed_recommedation_agent.reranker import (
    rerank,
    build_query_from_tags,
    build_document_from_pitchdeck,
    RERANK_FETCH_K,
)
from app.graph.feed_recommedation_agent.tools.embedding_tools import (
    sync_tags_to_qdrant,
    build_investor_embedding,
)

logger = get_logger(__name__)
TOP_K: int = int(os.getenv("TOP_K", "10"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pitchdeck_uuid(pitchdeck_id: str) -> str:
    try:
        return str(uuid.UUID(pitchdeck_id))
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, pitchdeck_id))


# ── Supabase fetchers ─────────────────────────────────────────────────────────

def fetch_pitchdeck_tags(pitchdeck_id: str) -> tuple[list[str], Optional[str]]:
    """Return (subtags, startup_id) for a single pitchdeck row."""
    if not supabase:
        logger.error("[PitchdeckTools] Supabase client not initialised.")
        return [], None

    resp = (
        supabase.table("pitchdecks")
        .select("tags, analysis, startup_id")
        .eq("pitchdeckid", pitchdeck_id)
        .single()
        .execute()
    )
    row        = resp.data or {}
    startup_id = row.get("startup_id")

    # Extract subtags from analysis.sub_tags (same taxonomy as investor Neo4j subtags)
    subtags = _extract_subtags(row.get("analysis"))

    # Fall back to main tags only if analysis has no subtags
    if not subtags:
        subtags = [t.strip().lower() for t in (row.get("tags") or []) if t.strip()]
        logger.warning("[PitchdeckTools] Pitchdeck %s has no subtags — using main tags.", pitchdeck_id)
    else:
        logger.info("[PitchdeckTools] Pitchdeck %s → %d subtags.", pitchdeck_id, len(subtags))

    return subtags, startup_id


def _extract_subtags(analysis) -> list[str]:
    """Flatten analysis.sub_tags dict into a list of subtag strings."""
    if not analysis:
        return []
    if isinstance(analysis, str):
        import json
        try:
            analysis = json.loads(analysis)
        except Exception:
            return []
    sub_tags_dict = analysis.get("sub_tags", {}) if isinstance(analysis, dict) else {}
    return [
        st.strip().lower()
        for subtags in sub_tags_dict.values()
        for st in subtags
        if st.strip()
    ]


def fetch_all_pitchdecks() -> list[dict]:
    """Return every pitchdeck row (pitchdeckid, tags, startup_id)."""
    if not supabase:
        logger.error("[PitchdeckTools] Supabase client not initialised.")
        return []
    resp = supabase.table("pitchdecks").select("pitchdeckid, tags, startup_id").execute()
    return resp.data or []


# ── Embedding pipeline ────────────────────────────────────────────────────────

async def build_pitchdeck_embedding(pitchdeck_id: str) -> Optional[list[float]]:
    """Compute a pitchdeck embedding as the L2-normalised mean of its tag vectors."""
    tags, _ = fetch_pitchdeck_tags(pitchdeck_id)
    if not tags:
        return None
    tag_map = await sync_tags_to_qdrant(tags)
    vecs    = [tag_map[t] for t in tags if t in tag_map]
    return aggregate_embeddings(vecs, strategy="mean") if vecs else None


def store_pitchdeck_embedding(
    pitchdeck_id: str,
    embedding   : list[float],
    tags        : list[str],
    startup_id  : Optional[str] = None,
) -> bool:
    """Upsert one pitchdeck point into Qdrant [pitchdecks]."""
    client  = get_qdrant()
    payload = {"pitchdeck_id": pitchdeck_id, "tags": tags}
    if startup_id:
        payload["startup_id"] = startup_id

    try:
        client.upsert(
            collection_name = "pitchdecks",
            points = [
                PointStruct(
                    id      = _pitchdeck_uuid(pitchdeck_id),
                    vector  = embedding,
                    payload = payload,
                )
            ],
        )
        logger.info("[PitchdeckTools] Stored pitchdeck %s in Qdrant.", pitchdeck_id)
        return True
    except Exception as e:
        logger.error("[PitchdeckTools] Failed to store %s: %s", pitchdeck_id, e)
        return False


async def build_and_store_pitchdeck_embedding(pitchdeck_id: str) -> bool:
    """Full pipeline for a single pitchdeck: fetch → embed → store."""
    tags, startup_id = fetch_pitchdeck_tags(pitchdeck_id)
    if not tags:
        return False
    tag_map   = await sync_tags_to_qdrant(tags)
    vecs      = [tag_map[t] for t in tags if t in tag_map]
    if not vecs:
        return False
    embedding = aggregate_embeddings(vecs, strategy="mean")
    return store_pitchdeck_embedding(pitchdeck_id, embedding, tags, startup_id)


async def build_and_store_all_pitchdecks() -> dict[str, bool]:
    """Batch-sync all pitchdecks: single Jina pass, then store each."""
    rows = fetch_all_pitchdecks()
    if not rows:
        return {}

    all_tags: set[str] = set()
    for row in rows:
        for t in (row.get("tags") or []):
            all_tags.add(t.strip().lower())

    tag_map = await sync_tags_to_qdrant(sorted(all_tags))

    results: dict[str, bool] = {}
    for row in rows:
        pd_id      = row["pitchdeckid"]
        startup_id = row.get("startup_id")
        tags       = [t.strip().lower() for t in (row.get("tags") or []) if t.strip()]
        vecs       = [tag_map[t] for t in tags if t in tag_map]
        if not vecs:
            results[pd_id] = False
            continue
        embedding      = aggregate_embeddings(vecs, strategy="mean")
        results[pd_id] = store_pitchdeck_embedding(pd_id, embedding, tags, startup_id)

    success = sum(v for v in results.values())
    logger.info("[PitchdeckTools] Batch sync: %d/%d stored.", success, len(results))
    return results


# ── Two-stage Recommendation ──────────────────────────────────────────────────

async def get_recommended_pitchdecks_for_investor(
    investor_id  : str,
    k            : Optional[int] = None,
    use_reranker : bool = True,
) -> list[dict]:
    """
    Two-stage recommendation: vector search → reranker → top-K.

    Stage 1 — Vector search
        Qdrant ANN retrieves the top-RERANK_FETCH_K candidates
        using the investor's aggregated tag embedding.
        Fast but approximate.

    Stage 2 — Reranker  (skipped if use_reranker=False)
        Jina cross-encoder scores each candidate against the investor's
        tag query string and re-orders them by true semantic relevance.
        Slower but more precise.

    Args:
        investor_id:   Supabase investor UUID.
        k:             Final number of results to return (default: TOP_K).
        use_reranker:  Set False to skip Stage 2 (vector-only mode).

    Returns:
        List of dicts ordered by relevance:
        [
          {
            "pitchdeck_id" : "...",
            "startup_id"   : "...",
            "tags"         : [...],
            "vector_score" : 0.91,   ← from Qdrant (always present)
            "rerank_score" : 0.97,   ← from Jina   (present when reranker used)
          },
          ...
        ]
    """
    client = get_qdrant()
    k      = k or TOP_K

    # ── Stage 1: Vector search ────────────────────────────────────────────────
    investor_tags   = []
    investor_vector = await build_investor_embedding(investor_id)
    if investor_vector is None:
        logger.warning("[PitchdeckTools] Investor %s has no tags.", investor_id)
        return []

    # Fetch investor tags for building the reranker query string
    from app.graph.feed_recommedation_agent.tools.tag_tools import fetch_investor_tags
    investor_tags = fetch_investor_tags(investor_id)

    # Fetch more candidates than needed so reranker can pick the best K
    fetch_limit = RERANK_FETCH_K if use_reranker else k

    try:
        res  = client.query_points(
            collection_name = "pitchdecks",
            query           = investor_vector,
            limit           = fetch_limit,
            with_payload    = True,
        )
        candidates = res.points
    except Exception as e:
        logger.error("[PitchdeckTools] Qdrant search failed: %s", e)
        return []

    if not candidates:
        return []

    # Build intermediate result dicts (preserving order from vector search)
    candidate_dicts = [
        {
            "pitchdeck_id": h.payload.get("pitchdeck_id"),
            "startup_id"  : h.payload.get("startup_id"),
            "tags"        : h.payload.get("tags", []),
            "vector_score": round(h.score, 4),
        }
        for h in candidates
    ]

    logger.info(
        "[PitchdeckTools] Stage 1 done: %d candidates from vector search.",
        len(candidate_dicts),
    )

    # ── Stage 2: Reranker ─────────────────────────────────────────────────────
    if not use_reranker:
        # Vector-only mode: just return top-K as-is
        return candidate_dicts[:k]

    query     = build_query_from_tags(investor_tags)
    documents = [build_document_from_pitchdeck(c) for c in candidate_dicts]

    try:
        rerank_results = await rerank(query=query, documents=documents, top_n=k)
    except Exception as e:
        # Reranker failure is non-fatal: fall back to vector search order
        logger.error(
            "[PitchdeckTools] Reranker failed — falling back to vector order. Error: %s", e
        )
        return candidate_dicts[:k]

    # Map reranker output (original index + new score) back to candidate dicts
    final: list[dict] = []
    for result in rerank_results:
        original_index  = result.get("index", 0)
        rerank_score    = result.get("relevance_score", 0.0)
        candidate       = candidate_dicts[original_index].copy()
        candidate["rerank_score"] = round(rerank_score, 4)
        final.append(candidate)

    logger.info(
        "[PitchdeckTools] Stage 2 done: reranked %d → returning top %d.",
        len(documents),
        len(final),
    )
    return final