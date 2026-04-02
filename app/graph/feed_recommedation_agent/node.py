"""
Feed Recommendation Agent — LangGraph Nodes
============================================
Three sequential nodes:
  fetch_tags_node  → embed_node  → store_node
"""
from app.core.logger import get_logger
from app.graph.feed_recommedation_agent.tools import (
    fetch_investor_tags,
    build_investor_embedding,
    store_investor_embedding,
    get_top_k_similar_investors,
)
from app.graph.feed_recommedation_agent.state import FeedRecommendationState

logger = get_logger(__name__)


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
    """Upsert the embedding into the Supabase vector table."""
    embedding = state.get("embedding")
    if not embedding:
        return {"stored": False, "errors": ["Skipping store: no embedding."]}
    ok = store_investor_embedding(state["investor_id"], embedding)
    return {"stored": ok}