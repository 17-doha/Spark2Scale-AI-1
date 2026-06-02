"""
app/graph/feed_recommedation_agent/node.py
===========================================
LangGraph node functions for the feed recommendation pipeline.

Dependency Inversion: all imports are explicit at module level (no lazy imports).
Single Responsibility: each node handles exactly one pipeline stage.
"""

import os
from qdrant_client.models import Filter, FieldCondition, MatchAny

from app.core.qdrant_client import get_qdrant
from app.core.logger import get_logger
from app.graph.feed_recommedation_agent.embedding import aggregate_embeddings
from app.graph.feed_recommedation_agent.reranker import rerank, build_query_from_tags, RERANK_FETCH_K
from app.graph.feed_recommedation_agent.tools.embedding_tools import sync_tags_to_qdrant
from app.graph.feed_recommedation_agent.tools.tag_tools import (
    fetch_investor_tags,
    get_investor_subtags,
    get_sibling_subtags,
    fetch_seen_pitchdeck_ids,
)
from app.graph.feed_recommedation_agent.tools import (
    build_investor_embedding,
    store_investor_embedding,
    get_top_k_similar_investors,
)
from app.graph.feed_recommedation_agent.tools.contrastive import (
    select_query_vector_ucb,
    increment_sub_vector_impressions,
)
from app.graph.feed_recommedation_agent.state import FilteredSearchState
from app.graph.feed_recommedation_agent.schema import FeedRecommendationState

logger = get_logger(__name__)
TOP_K: int = int(os.getenv("TOP_K", "10"))
FALLBACK_SIBLING_LIMIT: int = int(os.getenv("FALLBACK_SIBLING_LIMIT", "30"))


# ════════════════════════════════════════════════════════════════════════════
#  Shared helpers (extracted for reusability and testability)
# ════════════════════════════════════════════════════════════════════════════

def _parse_hits(points) -> list[dict]:
    """Convert Qdrant search hits into standardised candidate dicts."""
    return [
        {
            "pitchdeck_id": h.payload.get("pitchdeck_id"),
            "startup_id"  : h.payload.get("startup_id"),
            "tags"        : h.payload.get("tags", []),
            "vector_score": round(h.score, 4),
        }
        for h in points
    ]

# ════════════════════════════════════════════════════════════════════════════
#  Original investor embedding nodes  (used by the embed workflow)
# ════════════════════════════════════════════════════════════════════════════

async def fetch_tags_node(state: FeedRecommendationState) -> dict:
    """Fetch the investor's tags from Supabase."""
    investor_id = state["investor_id"]
    tags = fetch_investor_tags(investor_id)
    if not tags:
        return {"tags": [], "errors": [f"Investor {investor_id} has no tags."]}
    return {"tags": tags}


async def embed_node(state: FeedRecommendationState) -> dict:
    """Build the aggregated embedding from the investor's tags."""
    if not state.get("tags"):
        return {"embedding": None, "errors": ["Skipping embed: no tags available."]}
    try:
        vector = await build_investor_embedding(state["investor_id"])
        return {"embedding": vector}
    except Exception as e:
        logger.error(f"[embed_node] {e}")
        return {"embedding": None, "errors": [str(e)]}


async def store_node(state: FeedRecommendationState) -> dict:
    """Upsert the embedding into Qdrant [investors]."""
    embedding = state.get("embedding")
    if not embedding:
        return {"stored": False, "errors": ["Skipping store: no embedding."]}
    tags = state.get("tags", [])
    ok = store_investor_embedding(state["investor_id"], embedding, tags)
    return {"stored": ok}


# ════════════════════════════════════════════════════════════════════════════
#  Filtered search nodes  (used by the filtered_search workflow)
# ════════════════════════════════════════════════════════════════════════════

async def generate_filter_tags_node(state: FilteredSearchState) -> dict:
    """
    NODE 1 — Tag pre-filter list + seen-pitchdeck exclusion list.

    Fetches:
      • Real sub-tags from Neo4j for the Qdrant tag filter.
      • Already-seen pitchdeck IDs from Supabase so nodes 3 and 3b
        can exclude them from every ANN search.
    """
    investor_id = state["investor_id"]

    subtags     = get_investor_subtags(investor_id)
    seen_ids    = fetch_seen_pitchdeck_ids(investor_id)

    logger.info(
        "[Node1] investor=%s  subtags=%d  seen_pitchdecks=%d",
        investor_id, len(subtags), len(seen_ids),
    )
    return {
        "filter_tags"       : subtags,
        "seen_pitchdeck_ids": seen_ids,
    }

async def build_investor_vector_node(state: FilteredSearchState) -> dict:
    """
    NODE 2 — Investor query vector.

    Priority order:
      1. UCB sub-vector (Task 4) — if [investor_sub_vectors] is populated,
         picks the under-explored MainTag sub-vector via UCB.
      2. Aggregated fallback      — simple mean of all tag embeddings,
         used when sub-vectors haven't been built yet.

    Choosing the UCB sub-vector here means every Qdrant search in Node 3
    already benefits from multi-vector diversity without changing anything
    downstream.
    """

    investor_id = state["investor_id"]

    # ── Attempt 1: UCB sub-vector ────────────────────────────────────────────
    ucb_vector, selected_tag = select_query_vector_ucb(investor_id)
    if ucb_vector is not None:
        increment_sub_vector_impressions(investor_id, selected_tag)
        logger.info("[Node2] UCB sub-vector selected: tag='%s'.", selected_tag)
        return {"investor_vector": ucb_vector}

    # ── Attempt 2: aggregated fallback ───────────────────────────────────────
    tags = fetch_investor_tags(investor_id)
    if not tags:
        return {
            "investor_vector": None,
            "errors": [f"Investor {investor_id} has no tags."],
        }

    tag_map = await sync_tags_to_qdrant(tags)
    vecs    = [tag_map[t] for t in tags if t in tag_map]
    if not vecs:
        return {
            "investor_vector": None,
            "errors": ["Tag embeddings unavailable."],
        }

    logger.info("[Node2] Aggregated fallback vector used for investor %s.", investor_id)
    return {"investor_vector": aggregate_embeddings(vecs, strategy="mean")}

async def filtered_vector_search_node(state: FilteredSearchState) -> dict:
    """NODE 3 — Filtered Qdrant ANN search with automatic unfiltered fallback."""
    if state.get("investor_vector") is None:
        return {"candidates": [], "errors": ["No investor vector — skipping search."]}

    filter_tags = state.get("filter_tags", [])
    seen_ids    = state.get("seen_pitchdeck_ids", [])

    def _build_filter(tags: list[str], exclude_ids: list[str]):
        """
        Combine an optional tag 'should' clause with an optional pitchdeck
        'must_not' exclusion into a single Qdrant Filter.
        Returns None when both lists are empty.
        """
        should   = [FieldCondition(key="tags",         match=MatchAny(any=tags))]       if tags        else []
        must_not = [FieldCondition(key="pitchdeck_id", match=MatchAny(any=exclude_ids))] if exclude_ids else []

        if not should and not must_not:
            return None
        return Filter(
            should   = should   or None,
            must_not = must_not or None,
        )

    try:
        qdrant_filter = _build_filter(filter_tags, seen_ids)
        res = get_qdrant().query_points(
            collection_name = "pitchdecks",
            query           = state["investor_vector"],
            query_filter    = qdrant_filter,
            limit           = RERANK_FETCH_K,
            with_payload    = True,
        )
        candidates = _parse_hits(res.points)
        logger.info("[Node3] Filtered search → %d candidates.", len(candidates))

        # Filter returned nothing — retry without tag filter but keep seen exclusion
        if not candidates and filter_tags:
            logger.warning("[Node3] 0 filtered results — retrying without tag filter.")
            fallback_filter = _build_filter([], seen_ids)
            res = get_qdrant().query_points(
                collection_name = "pitchdecks",
                query           = state["investor_vector"],
                query_filter    = fallback_filter,
                limit           = RERANK_FETCH_K,
                with_payload    = True,
            )
            candidates = _parse_hits(res.points)
            logger.info("[Node3] Unfiltered fallback → %d candidates.", len(candidates))

        return {"candidates": candidates}
    except Exception as e:
        logger.error("[Node3] Qdrant search failed: %s", e)
        return {"candidates": [], "errors": [f"Qdrant search failed: {e}"]}       


async def rerank_candidates_node(state: FilteredSearchState) -> dict:
    """NODE 4 — Jina cross-encoder re-scores candidates → top-K. Non-fatal fallback on failure."""
    candidates = state.get("candidates", [])
    if not candidates:
        return {"final_results": [], "errors": ["No candidates to rerank."]}

    query     = build_query_from_tags(fetch_investor_tags(state["investor_id"]))
    documents = [" ".join(c.get("tags", [])) for c in candidates]

    try:
        rerank_results = await rerank(query=query, documents=documents, top_n=TOP_K)
    except Exception as e:
        logger.error("[Node4] Reranker failed — using vector order. %s", e)
        return {"final_results": candidates[:TOP_K], "errors": [f"Reranker fallback: {e}"]}

    final = []
    for r in rerank_results:
        c = candidates[r.get("index", 0)].copy()
        c["rerank_score"] = round(r.get("relevance_score", 0.0), 4)
        final.append(c)

    logger.info("[Node4] Reranked %d → top %d.", len(candidates), len(final))
    return {"final_results": final}


async def format_output_node(state: FilteredSearchState) -> dict:
    """NODE 5 — Passthrough. Add post-processing here (enrich, filter seen, threshold)."""
    results = state.get("final_results", [])
    logger.info("[Node5] Returning %d results for investor %s.", len(results), state["investor_id"])
    return {"final_results": results}


async def sibling_fallback_node(state: FilteredSearchState) -> dict:
    """
    NODE 3b — Sibling-tag fallback when node 3 returned fewer than TOP_K candidates.
    Excludes already-seen pitchdecks from the sibling search as well.
    """
    current_candidates = state.get("candidates", [])
    filter_tags        = state.get("filter_tags", [])
    investor_vector    = state.get("investor_vector")
    seen_ids           = state.get("seen_pitchdeck_ids", [])   # ← NEW

    if investor_vector is None:
        return {
            "fallback_triggered": False,
            "sibling_tags": [],
            "errors": ["Sibling fallback skipped: no investor vector."],
        }

    needed = TOP_K - len(current_candidates)
    if needed <= 0:
        return {"fallback_triggered": False, "sibling_tags": []}

    already_seen_ids = {c["pitchdeck_id"] for c in current_candidates} | set(seen_ids)  # ← UPDATED

    siblings = get_sibling_subtags(
        subtag_names=filter_tags,
        exclude=filter_tags,
        limit=FALLBACK_SIBLING_LIMIT,
    )

    if not siblings:
        logger.warning("[FallbackNode] No siblings found for filter_tags=%s", filter_tags)
        return {
            "fallback_triggered": True,
            "sibling_tags": [],
            "errors": ["Sibling fallback: no Neo4j siblings found."],
        }

    # Combine sibling tag filter with seen-pitchdeck exclusion
    must_not = (
        [FieldCondition(key="pitchdeck_id", match=MatchAny(any=list(already_seen_ids)))]
        if already_seen_ids else []
    )
    sibling_filter = Filter(
        should   = [FieldCondition(key="tags", match=MatchAny(any=siblings))],
        must_not = must_not or None,
    )

    try:
        res = get_qdrant().query_points(
            collection_name = "pitchdecks",
            query           = investor_vector,
            query_filter    = sibling_filter,
            limit           = needed * 2,
            with_payload    = True,
        )
        new_hits = [
            {
                "pitchdeck_id" : h.payload.get("pitchdeck_id"),
                "startup_id"   : h.payload.get("startup_id"),
                "tags"         : h.payload.get("tags", []),
                "vector_score" : round(h.score, 4),
                "from_fallback": True,
            }
            for h in res.points
            if h.payload.get("pitchdeck_id") not in already_seen_ids  # double-guard
        ]
    except Exception as e:
        logger.error("[FallbackNode] Qdrant sibling search failed: %s", e)
        return {
            "fallback_triggered": True,
            "sibling_tags": siblings,
            "errors": [f"Sibling fallback Qdrant error: {e}"],
        }

    merged = current_candidates + new_hits
    logger.info(
        "[FallbackNode] Merged %d original + %d sibling hits = %d total candidates.",
        len(current_candidates), len(new_hits), len(merged),
    )
    return {
        "candidates"        : merged,
        "fallback_triggered": True,
        "sibling_tags"      : siblings,
    }