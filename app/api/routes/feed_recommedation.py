"""
app/api/routes/feed_recommedation.py
=====================================
Feed recommendation API routes.

Single Responsibility: routes are thin — they parse requests, delegate to
services/tools, and return responses. Business logic lives in dedicated
service classes and tool modules.

All endpoint paths and response schemas are unchanged.
"""

import os

from fastapi import APIRouter, HTTPException, Request, Query, BackgroundTasks
from pydantic import BaseModel
from qdrant_client.models import Filter, FieldCondition, MatchAny

from app.core.limiter import api_limiter
from app.core.logger import get_logger
from app.core.qdrant_client import get_qdrant
from app.graph.feed_recommedation_agent.schema import (
    InvestorEmbeddingRequest,
    InvestorEmbeddingResponse,
    SimilarInvestorsResponse,
    PitchdeckEmbeddingRequest,
    PitchdeckEmbeddingResponse,
    RecommendedPitchdecksResponse,
)
from app.graph.feed_recommedation_agent.tools.pitchdeck_tools import (
    build_and_store_pitchdeck_embedding,
)
from app.graph.feed_recommedation_agent.tools.tag_tools import (
    fetch_investor_tags,
    get_investor_subtags,
    sync_supabase_to_neo4j,
    update_graph_edge_weights,
)
from app.graph.feed_recommedation_agent.tools import (
    build_and_store_investor_embedding,
    build_investor_embedding,
)
from app.graph.feed_recommedation_agent.tools.contrastive import (
    build_investor_sub_vectors,
    update_sub_vector_from_interaction,
)
from app.graph.feed_recommedation_agent.workflow import filtered_search_app
from app.graph.feed_recommedation_agent.rewards import InteractionType
from app.graph.feed_recommedation_agent.services.interaction_service import InteractionService
from app.graph.feed_recommedation_agent.services.sync_audit_service import SyncAuditService

router = APIRouter()
logger = get_logger(__name__)
TOP_K  = int(os.getenv("TOP_K", "10"))


class InteractionPayload(BaseModel):
    user_id: str
    pitch_id: str
    liked: bool
    contacted: bool

# ════════════════════════════════════════════════════════════════════════════
#  INVESTOR sync
# ════════════════════════════════════════════════════════════════════════════

@router.post("/investor-embedding", response_model=InvestorEmbeddingResponse)
@api_limiter.limit("30/minute")
async def upsert_investor_embedding(request: Request, payload: InvestorEmbeddingRequest):
    tags = fetch_investor_tags(payload.investor_id)
    if not tags:
        raise HTTPException(status_code=404, detail="Investor not found or has no tags.")
    ok = await build_and_store_investor_embedding(payload.investor_id)
    return InvestorEmbeddingResponse(
        investor_id = payload.investor_id,
        tags        = tags,
        stored      = ok,
        message     = "Stored successfully." if ok else "Failed to store embedding.",
    )


# ════════════════════════════════════════════════════════════════════════════
#  PITCHDECK sync
# ════════════════════════════════════════════════════════════════════════════

@router.post("/pitchdeck-embedding", response_model=PitchdeckEmbeddingResponse)
@api_limiter.limit("30/minute")
async def upsert_pitchdeck_embedding(request: Request, payload: PitchdeckEmbeddingRequest):
    ok = await build_and_store_pitchdeck_embedding(payload.pitchdeck_id)
    return PitchdeckEmbeddingResponse(
        pitchdeck_id = payload.pitchdeck_id,
        stored       = ok,
        message      = "Stored successfully." if ok else "Pitchdeck not found or failed.",
    )


# ════════════════════════════════════════════════════════════════════════════
#  SIMILAR INVESTORS  — tag-filtered
# ════════════════════════════════════════════════════════════════════════════

@router.get("/similar-investors/{investor_id}", response_model=SimilarInvestorsResponse)
@api_limiter.limit("60/minute")
async def get_similar_investors(request: Request, investor_id: str, k: int = TOP_K):
    """
    Top-K investors most similar to the given investor.
    ANN search runs only within investors whose tags overlap with filter_tags.
    """
    vector = await build_investor_embedding(investor_id)
    if vector is None:
        raise HTTPException(status_code=404, detail="Investor has no tags.")

    subtags = get_investor_subtags(investor_id)
    qdrant_filter = (
        Filter(should=[FieldCondition(key="tags", match=MatchAny(any=subtags))])
        if subtags else None
    )

    try:
        res = get_qdrant().query_points(
            collection_name = "investors",
            query           = vector,
            query_filter    = qdrant_filter,
            limit           = k + 1,         # +1 so we can drop self
            with_payload    = True,
        )
        results = [
            {
                "investor_id": h.payload.get("investor_id"),
                "similarity" : round(h.score, 4),
                "tags"       : h.payload.get("tags", []),
            }
            for h in res.points
            if h.payload.get("investor_id") != investor_id
        ][:k]
    except Exception as e:
        logger.error("[similar-investors] Qdrant search failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Search failed. Please try again.")

    return SimilarInvestorsResponse(investor_id=investor_id, results=results, k=k)

# ════════════════════════════════════════════════════════════════════════════
#  INTERACTIONS - Tags
# ════════════════════════════════════════════════════════════════════════════

@router.post("/interactions")
async def handle_interaction(payload: InteractionPayload, background_tasks: BackgroundTasks):
    """
    Process an investor interaction (like/dislike/contact) with a pitchdeck.
    Delegates business logic to InteractionService (SRP).
    """
    # 1. Resolve interaction type (centralised in enum — OCP/Liskov)
    action_type, interaction = InteractionType.from_payload(
        liked=payload.liked,
        contacted=payload.contacted,
    )

    # 2. Get reward config
    config_rl = InteractionService.get_reward_config(action_type)

    # 3. Fetch pitchdeck tags (delegated to service)
    try:
        tag_data = InteractionService.fetch_pitchdeck_tags(payload.pitch_id)
    except RuntimeError as e:
        logger.error("[interactions] Failed to fetch pitchdeck tags: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process interaction. Please try again.")

    parent_tags = tag_data["parent_tags"]
    sub_tags    = tag_data["sub_tags"]
    raw_tags    = tag_data["raw_tags"]

    # 4. Schedule background tasks
    background_tasks.add_task(
        update_graph_edge_weights,
        user_id      = payload.user_id,
        tag_names    = parent_tags,
        subtag_names = sub_tags,
        reward       = config_rl.reward,
        alpha        = config_rl.alpha,
    )

    background_tasks.add_task(
        update_sub_vector_from_interaction,
        investor_id    = payload.user_id,
        pitchdeck_id   = payload.pitch_id,
        interaction    = interaction,
        pitchdeck_tags = raw_tags or parent_tags,
    )

    return InteractionService.build_success_message(action_type, parent_tags)

@router.post("/sub-vectors/build/{investor_id}")
@api_limiter.limit("10/minute")
async def build_sub_vectors(request: Request, investor_id: str):
    """
    Build or rebuild per-MainTag sub-vectors for one investor.
    Call this once after onboarding, then let the /interactions endpoint
    keep vectors current via triplet updates.
    """
    results = await build_investor_sub_vectors(investor_id)
    ok      = sum(v for v in results.values())
    return {
        "investor_id": investor_id,
        "total"      : len(results),
        "stored"     : ok,
        "failed"     : len(results) - ok,
        "detail"     : results,
    }

@router.post("/admin/sync-neo4j")
async def trigger_manual_neo4j_sync(background_tasks: BackgroundTasks):
    """
    Manually triggers a full two-way sync between Supabase and Neo4j.
    This will add missing records and delete records in Neo4j that
    were removed from Supabase.
    """
    background_tasks.add_task(sync_supabase_to_neo4j)

    return {
        "status": "success",
        "message": "Full Supabase -> Neo4j sync started in the background. Check your logs for completion."
    }

@router.get("/admin/verify-sync")
async def verify_full_sync():
    """
    Audits the sync status between Supabase and Neo4j for BOTH tags and sub-tags.
    Delegates to SyncAuditService (SRP).
    """
    try:
        return SyncAuditService.verify()
    except RuntimeError:
        raise HTTPException(status_code=500, detail="Failed to connect to Neo4j.")

@router.get("/investors/{user_id}/subtags")
async def fetch_investor_subtags(
    user_id: str,
    hate_threshold: float = Query(default=0.01),
    limit: int = Query(default=50, ge=1, le=200),
):
    subtags = get_investor_subtags(
        user_id=user_id,
        hate_threshold=hate_threshold,
        limit=limit,
    )
    return {
        "status": "success",
        "user_id": user_id,
        "hate_threshold_applied": hate_threshold,
        "limit": limit,
        "subtag_count": len(subtags),
        "subtags": subtags,
    }

# ════════════════════════════════════════════════════════════════════════════
#  RECOMMEND  — full filtered LangGraph pipeline
# ════════════════════════════════════════════════════════════════════════════

@router.get("/recommend/{investor_id}", response_model=RecommendedPitchdecksResponse)
@api_limiter.limit("60/minute")
async def recommend_pitchdecks(request: Request, investor_id: str, k: int = TOP_K):
    result = await filtered_search_app.ainvoke({
        "investor_id"       : investor_id,
        "filter_tags"       : [],
        "investor_vector"   : None,
        "candidates"        : [],
        "final_results"     : [],
        "errors"            : [],
        "seen_pitchdeck_ids": [],
        "fallback_triggered": False,
        "sibling_tags"      : [],
    })

    final_results = result.get("final_results", [])

    return RecommendedPitchdecksResponse(
        investor_id = investor_id,
        results     = final_results[:k],
        k           = k,
    )

# ════════════════════════════════════════════════════════════════════════════
#  SUPABASE WEBHOOKS
# ════════════════════════════════════════════════════════════════════════════

@router.post("/webhook/investor")
async def webhook_investor(request: Request):
    body        = await request.json()
    event_type  = body.get("type", "")
    investor_id = body.get("record", {}).get("user_id")

    if not investor_id:
        return {"status": "skipped", "reason": "No user_id in record."}
    if event_type not in ("INSERT", "UPDATE"):
        return {"status": "skipped", "reason": f"Event '{event_type}' not handled."}

    ok = await build_and_store_investor_embedding(investor_id)
    return {"status": "synced" if ok else "failed", "investor_id": investor_id, "event": event_type}


@router.post("/webhook/pitchdeck")
async def webhook_pitchdeck(request: Request):
    body         = await request.json()
    event_type   = body.get("type", "")
    pitchdeck_id = body.get("record", {}).get("pitchdeckid")

    if not pitchdeck_id:
        return {"status": "skipped", "reason": "No pitchdeckid in record."}
    if event_type not in ("INSERT", "UPDATE"):
        return {"status": "skipped", "reason": f"Event '{event_type}' not handled."}

    ok = await build_and_store_pitchdeck_embedding(pitchdeck_id)
    return {"status": "synced" if ok else "failed", "pitchdeck_id": pitchdeck_id, "event": event_type}