"""
app/graph/feed_recommedation_agent/node.py
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
)
from app.graph.feed_recommedation_agent.tools import (
    build_investor_embedding,
    store_investor_embedding,
    get_top_k_similar_investors,
)
from app.graph.feed_recommedation_agent.state import FilteredSearchState
from app.graph.feed_recommedation_agent.schema import FeedRecommendationState

logger = get_logger(__name__)
TOP_K: int = int(os.getenv("TOP_K", "10"))


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
    NODE 1 — Tag pre-filter list for Qdrant.
    Fetches real sub-tags from Neo4j associated with the investor's interests.
    """
    subtags = get_investor_subtags(state["investor_id"])
    logger.info("[Node1] Found %d sub-tags for investor %s.", len(subtags), state["investor_id"])
    return {"filter_tags": subtags}


async def build_investor_vector_node(state: FilteredSearchState) -> dict:
    """NODE 2 — Investor aggregated tag embedding."""
    tags = fetch_investor_tags(state["investor_id"])
    if not tags:
        return {"investor_vector": None, "errors": [f"Investor {state['investor_id']} has no tags."]}

    tag_map = await sync_tags_to_qdrant(tags)
    vecs    = [tag_map[t] for t in tags if t in tag_map]
    if not vecs:
        return {"investor_vector": None, "errors": ["Tag embeddings unavailable."]}

    logger.info("[Node2] Built vector for investor %s (%d tags).", state["investor_id"], len(tags))
    return {"investor_vector": aggregate_embeddings(vecs, strategy="mean")}


async def filtered_vector_search_node(state: FilteredSearchState) -> dict:
    """
    NODE 3 — Qdrant ANN search within the tag-filtered subset only.
    Payload filter (MatchAny) runs before ANN — nearly free performance-wise.
    """
    if state.get("investor_vector") is None:
        return {"candidates": [], "errors": ["No investor vector — skipping search."]}

    filter_tags   = state.get("filter_tags", [])
    qdrant_filter = (
        Filter(should=[FieldCondition(key="tags", match=MatchAny(any=filter_tags))])
        if filter_tags else None
    )

    try:
        res = get_qdrant().query_points(
            collection_name = "pitchdecks",
            query           = state["investor_vector"],
            query_filter    = qdrant_filter,
            limit           = RERANK_FETCH_K,
            with_payload    = True,
        )
        candidates = [
            {
                "pitchdeck_id": h.payload.get("pitchdeck_id"),
                "startup_id"  : h.payload.get("startup_id"),
                "tags"        : h.payload.get("tags", []),
                "vector_score": round(h.score, 4),
            }
            for h in res.points
        ]
        logger.info("[Node3] filter_tags=%s → %d candidates.", filter_tags, len(candidates))
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