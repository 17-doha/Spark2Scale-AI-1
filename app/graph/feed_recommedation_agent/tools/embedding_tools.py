import os
from typing import Optional
from app.core.supabase_client import supabase
from app.core.logger import get_logger
from app.graph.feed_recommedation_agent.embedding import embed_texts, aggregate_embeddings
from app.graph.feed_recommedation_agent.tools.tag_tools import fetch_investor_tags, fetch_all_investors

logger = get_logger(__name__)
TOP_K: int = int(os.getenv("TOP_K", "10"))


async def build_investor_embedding(investor_id: str) -> Optional[list[float]]:
    tags = fetch_investor_tags(investor_id)
    if not tags:
        logger.warning(f"[EmbedTools] Investor {investor_id} has no tags.")
        return None
    embeddings = await embed_texts(tags)
    return aggregate_embeddings(embeddings, strategy="mean")


async def build_all_investor_embeddings() -> dict[str, list[float]]:
    investors = fetch_all_investors()
    results: dict[str, list[float]] = {}

    all_tags_set = set()
    for row in investors:
        for tag in (row.get("tags") or []):
            all_tags_set.add(tag.strip().lower())

    if not all_tags_set:
        return results

    unique_tags = sorted(all_tags_set)
    tag_vecs = await embed_texts(unique_tags)
    tag_to_vec = dict(zip(unique_tags, tag_vecs))

    for row in investors:
        investor_id = row["user_id"]
        tags = [t.strip().lower() for t in (row.get("tags") or []) if t.strip()]
        vecs = [tag_to_vec[t] for t in tags if t in tag_to_vec]
        if vecs:
            results[investor_id] = aggregate_embeddings(vecs, strategy="mean")

    logger.info(f"[EmbedTools] Built embeddings for {len(results)} investors.")
    return results


def store_investor_embedding(investor_id: str, embedding: list[float]) -> bool:
    if not supabase:
        logger.error("[EmbedTools] Supabase client is not initialised.")
        return False

    # pgvector via PostgREST requires the vector as a string "[0.1,0.2,...]"
    vector_str = "[" + ",".join(str(x) for x in embedding) + "]"

    try:
        supabase.table("investor_embeddings").upsert(
            {"investor_id": investor_id, "embedding": vector_str},
            on_conflict="investor_id",
        ).execute()
        logger.info(f"[EmbedTools] Stored embedding for investor {investor_id}.")
        return True
    except Exception as e:
        logger.error(f"[EmbedTools] Failed to store for {investor_id}: {e}")
        return False


async def build_and_store_investor_embedding(investor_id: str) -> bool:
    vector = await build_investor_embedding(investor_id)
    if vector is None:
        return False
    return store_investor_embedding(investor_id, vector)


async def build_and_store_all() -> dict[str, bool]:
    embeddings = await build_all_investor_embeddings()
    return {inv_id: store_investor_embedding(inv_id, vec) for inv_id, vec in embeddings.items()}


def get_top_k_similar_investors(query_embedding: list[float], k: Optional[int] = None) -> list[dict]:
    if not supabase:
        return []
    k = k or TOP_K
    vector_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    try:
        resp = supabase.rpc(
            "match_investors",
            {"query_embedding": vector_str, "match_count": k},
        ).execute()
        return resp.data or []
    except Exception as e:
        logger.error(f"[EmbedTools] Similarity search failed: {e}")
        return []