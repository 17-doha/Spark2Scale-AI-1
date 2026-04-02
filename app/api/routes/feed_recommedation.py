"""
app/api/routes/feed_recommedation.py
=====================================
Feed Recommendation API.

Key change: GET /feed/recommend/{investor_id} now accepts a `rerank` query param.
  ?rerank=true  (default) → two-stage: vector search + Jina reranker
  ?rerank=false            → vector search only (faster, less precise)
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Optional

from app.core.limiter import api_limiter
from app.core.logger import get_logger
from app.graph.feed_recommedation_agent.schema import (
    InvestorEmbeddingRequest,
    InvestorEmbeddingResponse,
    SimilarInvestorsResponse,
    PitchdeckEmbeddingRequest,
    PitchdeckEmbeddingResponse,
    RecommendedPitchdecksResponse,
)
from app.graph.feed_recommedation_agent.tools import (
    fetch_investor_tags,
    build_and_store_investor_embedding,
    build_investor_embedding,
    get_top_k_similar_investors,
)
from app.graph.feed_recommedation_agent.tools.pitchdeck_tools import (
    build_and_store_pitchdeck_embedding,
    get_recommended_pitchdecks_for_investor,
)
import os

router = APIRouter()
logger = get_logger(__name__)
TOP_K  = int(os.getenv("TOP_K", "10"))


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
#  SIMILARITY — investor ↔ investor
# ════════════════════════════════════════════════════════════════════════════

@router.get("/similar-investors/{investor_id}", response_model=SimilarInvestorsResponse)
@api_limiter.limit("60/minute")
async def get_similar_investors(request: Request, investor_id: str, k: int = TOP_K):
    vector = await build_investor_embedding(investor_id)
    if vector is None:
        raise HTTPException(status_code=404, detail="Investor has no tags.")
    results = get_top_k_similar_investors(vector, k=k)
    results = [r for r in results if r.get("investor_id") != investor_id]
    return SimilarInvestorsResponse(investor_id=investor_id, results=results, k=k)


# ════════════════════════════════════════════════════════════════════════════
#  RECOMMENDATION — investor → pitchdeck  (with optional reranker)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/recommend/{investor_id}", response_model=RecommendedPitchdecksResponse)
@api_limiter.limit("60/minute")
async def recommend_pitchdecks(
    request     : Request,
    investor_id : str,
    k           : int  = TOP_K,
    rerank      : bool = True,      # ?rerank=false to skip Stage 2
):
    """
    Recommend the top-K pitchdecks for a given investor.

    Two-stage pipeline (default):
      1. Vector search  — fast ANN retrieval from Qdrant [pitchdecks]
      2. Reranker       — Jina cross-encoder re-scores candidates for precision

    Each result includes:
      - pitchdeck_id, startup_id, tags
      - vector_score  (always)
      - rerank_score  (only when ?rerank=true)

    Use ?rerank=false for lower-latency responses where approximate ranking is acceptable.
    """
    results = await get_recommended_pitchdecks_for_investor(
        investor_id  = investor_id,
        k            = k,
        use_reranker = rerank,
    )

    if results is None:
        raise HTTPException(status_code=404, detail="Investor not found or has no tags.")

    return RecommendedPitchdecksResponse(investor_id=investor_id, results=results, k=k)


# ════════════════════════════════════════════════════════════════════════════
#  SUPABASE WEBHOOKS
# ════════════════════════════════════════════════════════════════════════════

@router.post("/webhook/investor")
async def webhook_investor(request: Request):
    """
    Triggered by Supabase on INSERT/UPDATE to `investors`.
    Configure in: Dashboard → Database → Webhooks
    URL: https://<your-api>/api/v1/feed/webhook/investor
    """
    body        = await request.json()
    event_type  = body.get("type", "")
    record      = body.get("record", {})
    investor_id = record.get("user_id")

    if not investor_id:
        return {"status": "skipped", "reason": "No user_id in record."}
    if event_type not in ("INSERT", "UPDATE"):
        return {"status": "skipped", "reason": f"Event '{event_type}' not handled."}

    logger.info("[Webhook] %s investors → syncing %s", event_type, investor_id)
    ok = await build_and_store_investor_embedding(investor_id)
    return {"status": "synced" if ok else "failed", "investor_id": investor_id, "event": event_type}


@router.post("/webhook/pitchdeck")
async def webhook_pitchdeck(request: Request):
    """
    Triggered by Supabase on INSERT/UPDATE to `pitchdecks`.
    Configure in: Dashboard → Database → Webhooks
    URL: https://<your-api>/api/v1/feed/webhook/pitchdeck
    """
    body         = await request.json()
    event_type   = body.get("type", "")
    record       = body.get("record", {})
    pitchdeck_id = record.get("pitchdeckid")

    if not pitchdeck_id:
        return {"status": "skipped", "reason": "No pitchdeckid in record."}
    if event_type not in ("INSERT", "UPDATE"):
        return {"status": "skipped", "reason": f"Event '{event_type}' not handled."}

    logger.info("[Webhook] %s pitchdecks → syncing %s", event_type, pitchdeck_id)
    ok = await build_and_store_pitchdeck_embedding(pitchdeck_id)
    return {"status": "synced" if ok else "failed", "pitchdeck_id": pitchdeck_id, "event": event_type}