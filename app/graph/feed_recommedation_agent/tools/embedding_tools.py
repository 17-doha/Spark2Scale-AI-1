"""
app/graph/feed_recommedation_agent/tools/embedding_tools.py
============================================================
Investor embedding pipeline — now backed by Qdrant.

Flow for one investor:
  tags (Supabase) → Jina embeddings → element-wise mean → Qdrant [investors]

Shared tag embeddings live in Qdrant [tags] and are reused across both
investors and pitchdecks to avoid redundant API calls.
"""

import os
import uuid
from typing import Optional

from qdrant_client.models import PointStruct

from app.core.qdrant_client import get_qdrant
from app.core.logger import get_logger
from app.graph.feed_recommedation_agent.embedding import embed_texts, aggregate_embeddings
from app.graph.feed_recommedation_agent.tools.tag_tools import (
    fetch_investor_tags,
    fetch_all_investors,
)

logger = get_logger(__name__)
TOP_K: int = int(os.getenv("TOP_K", "10"))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _tag_uuid(tag: str) -> str:
    """
    Deterministic UUID-v5 for a tag string so Qdrant gets a stable point ID.
    e.g. "fintech" → "3f2e4a1b-..."
    """
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, tag.strip().lower()))


def _investor_uuid(investor_id: str) -> str:
    """Ensure investor_id is a valid UUID string for Qdrant."""
    try:
        return str(uuid.UUID(investor_id))
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, investor_id))


# ── Tag cache (Qdrant [tags] collection) ─────────────────────────────────────

async def sync_tags_to_qdrant(tags: list[str]) -> dict[str, list[float]]:
    """
    For a list of tag strings:
      1. Check which ones are already in Qdrant [tags].
      2. Embed only the new ones via Jina.
      3. Upsert new tags into Qdrant [tags].
      4. Return a full {tag: vector} mapping for all requested tags.

    Args:
        tags: Unique tag strings to ensure are embedded.

    Returns:
        Dict mapping every tag string → its 768-dim vector.
    """
    client  = get_qdrant()
    tag_map : dict[str, list[float]] = {}

    if not tags:
        return tag_map

    # 1. Which tags are already stored?
    ids       = [_tag_uuid(t) for t in tags]
    existing  = client.retrieve("tags", ids=ids, with_vectors=True)
    found_ids = {p.id: p.vector for p in existing}

    new_tags: list[str] = []
    for tag, uid in zip(tags, ids):
        if uid in found_ids:
            tag_map[tag] = found_ids[uid]
        else:
            new_tags.append(tag)

    # 2. Embed only missing tags
    if new_tags:
        logger.info("[EmbedTools] Embedding %d new tag(s) via Jina.", len(new_tags))
        vectors = await embed_texts(new_tags)

        points = [
            PointStruct(
                id      = _tag_uuid(t),
                vector  = v,
                payload = {"tag": t},
            )
            for t, v in zip(new_tags, vectors)
        ]
        client.upsert(collection_name="tags", points=points)
        logger.info("[EmbedTools] Stored %d tag embeddings in Qdrant [tags].", len(points))

        for t, v in zip(new_tags, vectors):
            tag_map[t] = v

    return tag_map


# ── Investor embedding ────────────────────────────────────────────────────────

async def build_investor_embedding(investor_id: str) -> Optional[list[float]]:
    """
    Compute an investor's embedding as the L2-normalised mean of their tag vectors.

    Returns None if the investor has no tags.
    """
    tags = fetch_investor_tags(investor_id)
    if not tags:
        logger.warning("[EmbedTools] Investor %s has no tags.", investor_id)
        return None

    tag_map = await sync_tags_to_qdrant(tags)
    vecs    = [tag_map[t] for t in tags if t in tag_map]
    if not vecs:
        return None

    return aggregate_embeddings(vecs, strategy="mean")


def store_investor_embedding(
    investor_id: str,
    embedding  : list[float],
    tags       : list[str],
) -> bool:
    """
    Upsert one investor point into Qdrant [investors].

    Args:
        investor_id: UUID string.
        embedding:   768-dim vector.
        tags:        Raw tag list stored as metadata.
    """
    client = get_qdrant()
    try:
        client.upsert(
            collection_name = "investors",
            points = [
                PointStruct(
                    id      = _investor_uuid(investor_id),
                    vector  = embedding,
                    payload = {"investor_id": investor_id, "tags": tags},
                )
            ],
        )
        logger.info("[EmbedTools] Stored investor %s in Qdrant [investors].", investor_id)
        return True
    except Exception as e:
        logger.error("[EmbedTools] Failed to store investor %s: %s", investor_id, e)
        return False


async def build_and_store_investor_embedding(investor_id: str) -> bool:
    """Full pipeline: fetch tags → embed → store."""
    tags = fetch_investor_tags(investor_id)
    if not tags:
        return False
    tag_map   = await sync_tags_to_qdrant(tags)
    vecs      = [tag_map[t] for t in tags if t in tag_map]
    if not vecs:
        return False
    embedding = aggregate_embeddings(vecs, strategy="mean")
    return store_investor_embedding(investor_id, embedding, tags)


async def build_and_store_all() -> dict[str, bool]:
    """
    Batch-sync every investor in Supabase → Qdrant.

    Optimised: embeds all unique tags in a single Jina call, then
    reuses the cached vectors for every investor.
    """
    investors = fetch_all_investors()
    if not investors:
        return {}

    # 1. Collect all unique tags across all investors
    all_tags: set[str] = set()
    for row in investors:
        for t in (row.get("tags") or []):
            all_tags.add(t.strip().lower())

    # 2. Sync all tags to Qdrant in one pass (batches internally)
    tag_map = await sync_tags_to_qdrant(sorted(all_tags))

    # 3. Build and store each investor's embedding
    results: dict[str, bool] = {}
    for row in investors:
        inv_id = row["user_id"]
        tags   = [t.strip().lower() for t in (row.get("tags") or []) if t.strip()]
        vecs   = [tag_map[t] for t in tags if t in tag_map]
        if not vecs:
            results[inv_id] = False
            continue
        embedding        = aggregate_embeddings(vecs, strategy="mean")
        results[inv_id]  = store_investor_embedding(inv_id, embedding, tags)

    success = sum(v for v in results.values())
    logger.info("[EmbedTools] Batch sync done: %d/%d investors stored.", success, len(results))
    return results

# ── Similarity search ─────────────────────────────────────────────────────────

def get_top_k_similar_investors(
    query_embedding: list[float],
    k: Optional[int] = None,
) -> list[dict]:
    """
    Find the top-k investors whose embedding is closest to query_embedding.

    Returns:
        List of dicts: [{"investor_id": "...", "similarity": 0.95, "tags": [...]}]
    """
    client = get_qdrant()
    k      = k or TOP_K
    try:
        res = client.query_points(
            collection_name = "investors",
            query           = query_embedding,
            limit           = k,
            with_payload    = True,
        )
        hits = res.points
        return [
            {
                "investor_id": h.payload.get("investor_id"),
                "similarity" : round(h.score, 4),
                "tags"        : h.payload.get("tags", []),
            }
            for h in hits
        ]
    except Exception as e:
        logger.error("[EmbedTools] Investor similarity search failed: %s", e)
        return []