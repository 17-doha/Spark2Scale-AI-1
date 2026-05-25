"""
Contrastive Learning + UCB Multi-Vector Module.

Each investor owns one sub-vector per MainTag stored in the Qdrant
[investor_sub_vectors] collection. Two mechanisms act on these vectors:

  UCB selection  — at query time, the sub-vector with the highest
                   exploration score is used as the Qdrant query,
                   preventing a permanent filter bubble around the
                   investor's most-clicked tag.

  Triplet update — after each interaction, the relevant sub-vector is
                   nudged via:
                       E_new = E_old + α·(E_pos − E_old) − γ·(E_neg − E_old)
                   then L2-normalised and pushed back to Qdrant.
"""

import math
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from qdrant_client.models import (
    Distance, Filter, FieldCondition, MatchValue,
    PointStruct, VectorParams,
)

from app.core.qdrant_client import get_qdrant, EMBEDDING_DIM
from app.core.logger import get_logger
from app.graph.feed_recommedation_agent.embedding import aggregate_embeddings
from app.graph.feed_recommedation_agent.tools.embedding_tools import sync_tags_to_qdrant
from app.graph.feed_recommedation_agent.tools.tag_tools import fetch_investor_tags

logger = get_logger(__name__)

# ── Hyper-parameters ──────────────────────────────────────────────────────────
TRIPLET_ALPHA      = float(os.getenv("TRIPLET_ALPHA",    "0.30"))
TRIPLET_GAMMA      = float(os.getenv("TRIPLET_GAMMA",    "0.10"))
UCB_C_VECTOR       = float(os.getenv("UCB_C_VECTOR",     "1.414"))
CONTACT_ALPHA_MULT = float(os.getenv("CONTACT_ALPHA_MULT","1.50"))
SUB_VEC_COLLECTION = "investor_sub_vectors"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sub_vector_id(investor_id: str, tag_name: str) -> str:
    """Stable, deterministic UUID for one (investor, MainTag) pair."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{investor_id}:{tag_name.strip().lower()}"))


def _pitchdeck_point_id(pitchdeck_id: str) -> str:
    try:
        return str(uuid.UUID(pitchdeck_id))
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, pitchdeck_id))


def _l2_normalize(vec: np.ndarray) -> list[float]:
    norm = np.linalg.norm(vec)
    return (vec / norm if norm > 0 else vec).tolist()


def _ensure_collection() -> None:
    """Idempotent: create [investor_sub_vectors] and its payload indexes if absent."""
    client   = get_qdrant()
    existing = {c.name for c in client.get_collections().collections}

    if SUB_VEC_COLLECTION not in existing:
        client.create_collection(
            collection_name = SUB_VEC_COLLECTION,
            vectors_config  = VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        logger.info("[Contrastive] Created collection '%s'.", SUB_VEC_COLLECTION)

    # Indexes are idempotent — safe to call on every startup even if they exist.
    # investor_id is required for the scroll filter in select_query_vector_ucb().
    from qdrant_client.models import PayloadSchemaType
    client.create_payload_index(
        collection_name=SUB_VEC_COLLECTION,
        field_name="investor_id",
        field_schema=PayloadSchemaType.KEYWORD,
    )
    # tag_name is used for point ID lookups; index it too for future range queries.
    client.create_payload_index(
        collection_name=SUB_VEC_COLLECTION,
        field_name="tag_name",
        field_schema=PayloadSchemaType.KEYWORD,
    )
    logger.info("[Contrastive] Ensured payload indexes on '%s'.", SUB_VEC_COLLECTION)

# ── Sub-vector building ───────────────────────────────────────────────────────

async def build_investor_sub_vectors(investor_id: str) -> dict[str, bool]:
    """
    Build one sub-vector per MainTag and upsert into [investor_sub_vectors].

    Reuses embeddings already cached in Qdrant [tags] — no extra Jina calls.
    Sub-vector(tag) = L2-norm( mean of that tag's SubTag embeddings ).

    Safe to call repeatedly: existing vectors are overwritten with fresh ones,
    resetting stale embeddings after a major tag restructure.

    Returns {tag_name: stored_ok}.
    """
    _ensure_collection()

    main_tags = fetch_investor_tags(investor_id)
    if not main_tags:
        return {}

    # Fetch each MainTag's SubTags from Neo4j
    subtags_per_tag: dict[str, list[str]] = {}
    try:
        from neo4j import GraphDatabase
        from app.core.config import config
        driver = GraphDatabase.driver(
            config.NEO4J_URI,
            auth=(config.NEO4J_USERNAME, config.NEO4J_PASSWORD),
        )
        with driver.session() as s:
            for tag in main_tags:
                rows = s.run(
                    "MATCH (t:Tag {name:$tag})-[:CONTAINS]->(st:SubTag) RETURN st.name AS n",
                    tag=tag,
                )
                subtags_per_tag[tag] = [r["n"] for r in rows]
        driver.close()
    except Exception as e:
        logger.warning("[Contrastive] Neo4j subtag fetch failed (%s) — using tag name only.", e)

    # Fall back: embed the tag name itself when no subtags exist
    for tag in main_tags:
        if not subtags_per_tag.get(tag):
            subtags_per_tag[tag] = [tag]

    # Sync all subtags into Qdrant [tags] in a single Jina pass
    all_subtags = list({st for sts in subtags_per_tag.values() for st in sts})
    tag_map     = await sync_tags_to_qdrant(all_subtags)

    client  = get_qdrant()
    results: dict[str, bool] = {}

    for tag, subtags in subtags_per_tag.items():
        vecs = [tag_map[st] for st in subtags if st in tag_map]
        if not vecs:
            results[tag] = False
            continue

        sub_vec = aggregate_embeddings(vecs, strategy="mean")
        try:
            client.upsert(
                collection_name = SUB_VEC_COLLECTION,
                points = [PointStruct(
                    id      = _sub_vector_id(investor_id, tag),
                    vector  = sub_vec,
                    payload = {
                        "investor_id" : investor_id,
                        "tag_name"    : tag,
                        "impressions" : 0,
                        "last_updated": datetime.now(timezone.utc).isoformat(),
                    },
                )],
            )
            results[tag] = True
        except Exception as e:
            logger.error("[Contrastive] Store failed for %s/%s: %s", investor_id, tag, e)
            results[tag] = False

    logger.info(
        "[Contrastive] Built sub-vectors for %s: %d ok / %d failed.",
        investor_id,
        sum(v for v in results.values()),
        sum(not v for v in results.values()),
    )
    return results


# ── UCB sub-vector selection ──────────────────────────────────────────────────

def select_query_vector_ucb(investor_id: str) -> tuple[Optional[list[float]], Optional[str]]:
    """
    Pick the sub-vector with the highest UCB exploration score.

        UCB_i = 1.0 + C · √(ln N / n_i)     (n_i > 0)
        UCB_i = ∞                             (n_i = 0, never queried)

    The constant prior of 1.0 keeps the formula symmetric — the reranker
    handles result quality, UCB handles query diversity.

    Returns:
        (vector, tag_name) of the winning sub-vector, or (None, None).
    """
    _ensure_collection()
    client = get_qdrant()

    try:
        points, _ = client.scroll(
            collection_name = SUB_VEC_COLLECTION,
            scroll_filter   = Filter(must=[FieldCondition(
                key="investor_id", match=MatchValue(value=investor_id)
            )]),
            with_vectors = True,
            with_payload = True,
            limit        = 100,
        )
    except Exception as e:
        logger.error("[Contrastive] UCB scroll failed: %s", e)
        return None, None

    if not points:
        return None, None

    N          = sum(p.payload.get("impressions", 0) for p in points)
    best_score = -float("inf")
    best_point = None

    for p in points:
        n_i = p.payload.get("impressions", 0)
        ucb = float("inf") if (n_i == 0 or N == 0) else \
              1.0 + UCB_C_VECTOR * math.sqrt(math.log(N) / n_i)
        if ucb > best_score:
            best_score = ucb
            best_point = p

    tag = best_point.payload.get("tag_name")
    logger.info(
        "[Contrastive] UCB selected tag='%s' for investor %s (n_i=%d, N=%d).",
        tag, investor_id, best_point.payload.get("impressions", 0), N,
    )
    return best_point.vector, tag


def increment_sub_vector_impressions(investor_id: str, tag_name: str) -> None:
    """Bump the impression counter for the sub-vector that was just queried."""
    client   = get_qdrant()
    point_id = _sub_vector_id(investor_id, tag_name)
    try:
        existing = client.retrieve(
            SUB_VEC_COLLECTION, ids=[point_id], with_payload=True
        )
        if not existing:
            return
        client.set_payload(
            collection_name = SUB_VEC_COLLECTION,
            payload = {
                "impressions" : existing[0].payload.get("impressions", 0) + 1,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            },
            points = [point_id],
        )
    except Exception as e:
        logger.warning("[Contrastive] Impression increment failed %s/%s: %s", investor_id, tag_name, e)


# ── Triplet margin update ─────────────────────────────────────────────────────

def get_pitchdeck_vector(pitchdeck_id: str) -> Optional[list[float]]:
    """Fetch an existing pitchdeck embedding from Qdrant [pitchdecks]."""
    try:
        hits = get_qdrant().retrieve(
            collection_name = "pitchdecks",
            ids             = [_pitchdeck_point_id(pitchdeck_id)],
            with_vectors    = True,
        )
        return hits[0].vector if hits else None
    except Exception as e:
        logger.error("[Contrastive] Pitchdeck vector fetch failed %s: %s", pitchdeck_id, e)
        return None


def _resolve_target_tag(investor_id: str, pitchdeck_tags: list[str]) -> Optional[str]:
    """
    Find the investor MainTag that best overlaps with the pitchdeck's tags.
    This decides which sub-vector to update.
    Falls back to the first investor tag if no overlap is found.
    """
    investor_tags = {t.lower() for t in fetch_investor_tags(investor_id)}
    for tag in pitchdeck_tags:
        if tag.lower() in investor_tags:
            return tag.lower()
    return next(iter(investor_tags), None)


def triplet_update(
    investor_id : str,
    tag_name    : str,
    e_pos       : Optional[list[float]] = None,
    e_neg       : Optional[list[float]] = None,
    alpha       : float = TRIPLET_ALPHA,
    gamma       : float = TRIPLET_GAMMA,
) -> bool:
    """
    Update one investor sub-vector using Triplet Margin Loss:

        E_new = E_old + α·(E_pos − E_old) − γ·(E_neg − E_old)

    Either term is skipped when its vector is None:
        LIKE    → e_pos set, e_neg=None  → pull only
        DISLIKE → e_pos=None, e_neg set  → push only
        CONTACT → both set               → full triplet update

    The result is L2-normalised before being written to Qdrant.
    """
    if e_pos is None and e_neg is None:
        logger.warning("[Triplet] No pos or neg vector supplied — skipping.")
        return False

    client   = get_qdrant()
    point_id = _sub_vector_id(investor_id, tag_name)

    try:
        existing = client.retrieve(
            SUB_VEC_COLLECTION, ids=[point_id], with_vectors=True, with_payload=True
        )
    except Exception as e:
        logger.error("[Triplet] Retrieve failed %s/%s: %s", investor_id, tag_name, e)
        return False

    if not existing:
        logger.warning("[Triplet] Sub-vector not found for %s/%s — call build first.", investor_id, tag_name)
        return False

    e_old = np.array(existing[0].vector, dtype=np.float32)

    # Build delta — only include terms where a vector was supplied
    delta = np.zeros_like(e_old)
    if e_pos is not None:
        delta += alpha * (np.array(e_pos, dtype=np.float32) - e_old)
    if e_neg is not None:
        delta -= gamma * (np.array(e_neg, dtype=np.float32) - e_old)

    e_new = _l2_normalize(e_old + delta)

    try:
        client.upsert(
            collection_name = SUB_VEC_COLLECTION,
            points = [PointStruct(
                id      = point_id,
                vector  = e_new,
                payload = {
                    "investor_id" : investor_id,
                    "tag_name"    : tag_name,
                    "impressions" : existing[0].payload.get("impressions", 0) + 1,
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                },
            )],
        )
        logger.info(
            "[Triplet] Updated %s/%s  α=%.2f  γ=%.2f  pos=%s  neg=%s.",
            investor_id, tag_name, alpha, gamma,
            e_pos is not None, e_neg is not None,
        )
        return True
    except Exception as e:
        logger.error("[Triplet] Upsert failed %s/%s: %s", investor_id, tag_name, e)
        return False


# ── Interaction orchestrator ──────────────────────────────────────────────────

async def update_sub_vector_from_interaction(
    investor_id    : str,
    pitchdeck_id   : str,
    interaction    : str,           # "like" | "dislike" | "contact"
    pitchdeck_tags : list[str],
) -> bool:
    """
    Called from the /interactions endpoint after Neo4j weight updates.

    1. Fetches pitchdeck embedding from Qdrant [pitchdecks].
    2. Resolves which investor MainTag sub-vector to update (tag overlap).
    3. Dispatches triplet_update with the right pos/neg configuration.

    Interaction → update shape:
        like    : pull only   (e_pos=pitchdeck, e_neg=None)
        contact : pull only   (e_pos=pitchdeck, e_neg=None, alpha × CONTACT_ALPHA_MULT)
        dislike : push only   (e_pos=None, e_neg=pitchdeck)
    """
    pd_vector = get_pitchdeck_vector(pitchdeck_id)
    if pd_vector is None:
        logger.warning("[Contrastive] No vector for pitchdeck %s — skipping.", pitchdeck_id)
        return False

    target_tag = _resolve_target_tag(investor_id, pitchdeck_tags)
    if not target_tag:
        logger.warning("[Contrastive] No resolvable MainTag for investor %s.", investor_id)
        return False

    if interaction == "contact":
        alpha = min(TRIPLET_ALPHA * CONTACT_ALPHA_MULT, 0.90)
        return triplet_update(investor_id, target_tag, e_pos=pd_vector, alpha=alpha)
    elif interaction == "like":
        return triplet_update(investor_id, target_tag, e_pos=pd_vector)
    elif interaction == "dislike":
        return triplet_update(investor_id, target_tag, e_neg=pd_vector)

    return False