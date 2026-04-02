"""
app/graph/feed_recommedation_agent/tools/pitchdeck_tools.py
===========================================================
Pitchdeck embedding pipeline + investor → pitchdeck recommendation.

Flow:
  tags (Supabase pitchdecks) → sync to Qdrant [tags] → aggregate → Qdrant [pitchdecks]

Recommendation:
  investor_id → build/fetch investor vector → search Qdrant [pitchdecks] → top-K results
"""

import os
import uuid
from typing import Optional

from qdrant_client.models import PointStruct

from app.core.qdrant_client import get_qdrant
from app.core.supabase_client import supabase
from app.core.logger import get_logger
from app.graph.feed_recommedation_agent.embedding import aggregate_embeddings
from app.graph.feed_recommedation_agent.tools.embedding_tools import (
    sync_tags_to_qdrant,
    build_investor_embedding,
    _investor_uuid,
)

logger = get_logger(__name__)
TOP_K: int = int(os.getenv("TOP_K", "10"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pitchdeck_uuid(pitchdeck_id: str) -> str:
    """Ensure pitchdeck_id is a valid UUID string for Qdrant."""
    try:
        return str(uuid.UUID(pitchdeck_id))
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, pitchdeck_id))


# ── Supabase fetchers ─────────────────────────────────────────────────────────

def fetch_pitchdeck_tags(pitchdeck_id: str) -> tuple[list[str], Optional[str]]:
    """
    Return (tags, startup_id) for a single pitchdeck row.

    Returns:
        Tuple of (tag_list, startup_id).  tag_list is [] if not found.
    """
    if not supabase:
        logger.error("[PitchdeckTools] Supabase client not initialised.")
        return [], None

    resp = (
        supabase.table("pitchdecks")
        .select("tags, startup_id")
        .eq("pitchdeckid", pitchdeck_id)
        .single()
        .execute()
    )
    row        = resp.data or {}
    tags       = [t.strip().lower() for t in (row.get("tags") or []) if t.strip()]
    startup_id = row.get("startup_id")
    logger.info("[PitchdeckTools] Pitchdeck %s → %d tags.", pitchdeck_id, len(tags))
    return tags, startup_id


def fetch_all_pitchdecks() -> list[dict]:
    """
    Return every pitchdeck row (id, tags, startup_id).
    """
    if not supabase:
        logger.error("[PitchdeckTools] Supabase client not initialised.")
        return []

    resp = supabase.table("pitchdecks").select("pitchdeckid, tags, startup_id").execute()
    return resp.data or []


# ── Embedding pipeline ────────────────────────────────────────────────────────

async def build_pitchdeck_embedding(pitchdeck_id: str) -> Optional[list[float]]:
    """
    Compute a pitchdeck embedding as the L2-normalised mean of its tag vectors.

    Reuses the shared [tags] Qdrant collection — no redundant Jina calls.
    """
    tags, _ = fetch_pitchdeck_tags(pitchdeck_id)
    if not tags:
        return None

    tag_map = await sync_tags_to_qdrant(tags)          # shared tag cache
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
        logger.info("[PitchdeckTools] Stored pitchdeck %s in Qdrant [pitchdecks].", pitchdeck_id)
        return True
    except Exception as e:
        logger.error("[PitchdeckTools] Failed to store pitchdeck %s: %s", pitchdeck_id, e)
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
    """
    Batch-sync all pitchdecks to Qdrant.

    Optimised: one Jina pass for all unique tags, then reuses cache per pitchdeck.
    """
    rows = fetch_all_pitchdecks()
    if not rows:
        return {}

    # 1. Collect all unique tags
    all_tags: set[str] = set()
    for row in rows:
        for t in (row.get("tags") or []):
            all_tags.add(t.strip().lower())

    # 2. Sync all unique tags at once
    tag_map = await sync_tags_to_qdrant(sorted(all_tags))

    # 3. Build + store each pitchdeck
    results: dict[str, bool] = {}
    for row in rows:
        pd_id      = row["pitchdeckid"]
        startup_id = row.get("startup_id")
        tags       = [t.strip().lower() for t in (row.get("tags") or []) if t.strip()]
        vecs       = [tag_map[t] for t in tags if t in tag_map]
        if not vecs:
            results[pd_id] = False
            continue
        embedding       = aggregate_embeddings(vecs, strategy="mean")
        results[pd_id]  = store_pitchdeck_embedding(pd_id, embedding, tags, startup_id)

    success = sum(v for v in results.values())
    logger.info("[PitchdeckTools] Batch sync: %d/%d pitchdecks stored.", success, len(results))
    return results


# ── Recommendation ────────────────────────────────────────────────────────────

async def get_recommended_pitchdecks_for_investor(
    investor_id: str,
    k          : Optional[int] = None,
) -> list[dict]:
    """
    Nearest-neighbour search: given an investor, find the top-K most similar
    pitchdecks from Qdrant [pitchdecks].

    Algorithm:
      1. Build the investor's embedding (from their tags, via [tags] cache).
      2. Query Qdrant [pitchdecks] for the k nearest vectors.
      3. Return enriched results.

    Returns:
        List of dicts:
        [{"pitchdeck_id": "...", "startup_id": "...", "similarity": 0.92, "tags": [...]}]
    """
    client = get_qdrant()
    k      = k or TOP_K

    # Step 1 — get investor vector
    investor_vector = await build_investor_embedding(investor_id)
    if investor_vector is None:
        logger.warning("[PitchdeckTools] Investor %s has no tags — cannot recommend.", investor_id)
        return []

    # Step 2 — nearest-neighbour search in [pitchdecks]
    try:
        res = client.query_points(
            collection_name = "pitchdecks",
            query           = investor_vector,
            limit           = k,
            with_payload    = True,
        )
        hits = res.points
    except Exception as e:
        logger.error("[PitchdeckTools] Qdrant search failed: %s", e)
        return []

    # Step 3 — format results
    return [
        {
            "pitchdeck_id": h.payload.get("pitchdeck_id"),
            "startup_id"  : h.payload.get("startup_id"),
            "similarity"  : round(h.score, 4),
            "tags"        : h.payload.get("tags", []),
        }
        for h in hits
    ]