"""
app/api/routes/feed_recommedation.py
=====================================
Feed Recommendation API — all investor + pitchdeck sync/recommendation endpoints.

Webhook endpoints (called by Supabase Database Webhooks):
  POST /feed/webhook/investor    ← triggers on INSERT/UPDATE in `investors`
  POST /feed/webhook/pitchdeck   ← triggers on INSERT/UPDATE in `pitchdecks`

Manual / batch endpoints:
  POST /feed/investor-embedding           → sync one investor
  POST /feed/investor-embedding/batch     → sync all investors
  POST /feed/pitchdeck-embedding          → sync one pitchdeck
  POST /feed/pitchdeck-embedding/batch    → sync all pitchdecks

Query endpoints:
  GET  /feed/similar-investors/{investor_id}           → investor ↔ investor similarity
  GET  /feed/recommend/{investor_id}                   → investor → top-K pitchdeck recs
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
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

router  = APIRouter()
logger  = get_logger(__name__)
TOP_K   = int(os.getenv("TOP_K", "10"))


# ════════════════════════════════════════════════════════════════════════════
#  INVESTOR — single + batch sync
# ════════════════════════════════════════════════════════════════════════════

@router.post("/investor-embedding", response_model=InvestorEmbeddingResponse)
@api_limiter.limit("30/minute")
async def upsert_investor_embedding(request: Request, payload: InvestorEmbeddingRequest):
    """Sync one investor's embedding to Qdrant [investors]."""
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
#  PITCHDECK — single + batch sync
# ════════════════════════════════════════════════════════════════════════════

@router.post("/pitchdeck-embedding", response_model=PitchdeckEmbeddingResponse)
@api_limiter.limit("30/minute")
async def upsert_pitchdeck_embedding(request: Request, payload: PitchdeckEmbeddingRequest):
    """Sync one pitchdeck's embedding to Qdrant [pitchdecks]."""
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
    """Return the top-K investors most similar to the given investor."""
    vector = await build_investor_embedding(investor_id)
    if vector is None:
        raise HTTPException(status_code=404, detail="Investor has no tags — cannot compute similarity.")

    results = get_top_k_similar_investors(vector, k=k)
    # Exclude the investor themselves from results
    results = [r for r in results if r.get("investor_id") != investor_id]

    return SimilarInvestorsResponse(investor_id=investor_id, results=results, k=k)


# ════════════════════════════════════════════════════════════════════════════
#  RECOMMENDATION — investor → pitchdeck
# ════════════════════════════════════════════════════════════════════════════

@router.get("/recommend/{investor_id}", response_model=RecommendedPitchdecksResponse)
@api_limiter.limit("60/minute")
async def recommend_pitchdecks(request: Request, investor_id: str, k: int = TOP_K):
    """
    Given an investor, return the top-K most relevant pitchdecks.

    Uses the investor's aggregated tag embedding as the query vector
    and performs nearest-neighbour search in Qdrant [pitchdecks].
    """
    results = await get_recommended_pitchdecks_for_investor(investor_id, k=k)

    if results is None:
        raise HTTPException(status_code=404, detail="Investor not found or has no tags.")

    return RecommendedPitchdecksResponse(investor_id=investor_id, results=results, k=k)


# ════════════════════════════════════════════════════════════════════════════
#  SUPABASE WEBHOOKS — adaptive / real-time sync
# ════════════════════════════════════════════════════════════════════════════
#
#  Configure these in Supabase:
#    Dashboard → Database → Webhooks → Create Webhook
#
#    Table: investors  → Events: INSERT, UPDATE
#    URL:   https://<your-api>/api/v1/feed/webhook/investor
#    HTTP Method: POST
#    Headers: { "x-webhook-secret": "<your-secret>" }
#
#    Table: pitchdecks → Events: INSERT, UPDATE
#    URL:   https://<your-api>/api/v1/feed/webhook/pitchdeck


@router.post("/webhook/investor")
async def webhook_investor(request: Request):
    """
    Supabase fires this on every INSERT or UPDATE to the `investors` table.

    Payload from Supabase:
    {
      "type": "INSERT" | "UPDATE",
      "table": "investors",
      "record": { "user_id": "...", "tags": [...], ... },
      "old_record": { ... }   ← only on UPDATE
    }
    """
    body       = await request.json()
    event_type = body.get("type", "")
    record     = body.get("record", {})
    investor_id = record.get("user_id")

    if not investor_id:
        return {"status": "skipped", "reason": "No user_id in record."}

    if event_type not in ("INSERT", "UPDATE"):
        return {"status": "skipped", "reason": f"Event type '{event_type}' not handled."}

    logger.info("[Webhook] %s on investors → syncing investor %s", event_type, investor_id)
    ok = await build_and_store_investor_embedding(investor_id)

    return {
        "status"     : "synced" if ok else "failed",
        "investor_id": investor_id,
        "event"      : event_type,
    }


@router.post("/webhook/pitchdeck")
async def webhook_pitchdeck(request: Request):
    """
    Supabase fires this on every INSERT or UPDATE to the `pitchdecks` table.

    Payload from Supabase:
    {
      "type": "INSERT" | "UPDATE",
      "table": "pitchdecks",
      "record": { "id": "...", "tags": [...], "startup_id": "..." },
    }
    """
    body         = await request.json()
    event_type   = body.get("type", "")
    record       = body.get("record", {})
    pitchdeck_id = record.get("pitchdeckid")

    if not pitchdeck_id:
        return {"status": "skipped", "reason": "No pitchdeckid in record."}

    if event_type not in ("INSERT", "UPDATE"):
        return {"status": "skipped", "reason": f"Event type '{event_type}' not handled."}

    logger.info("[Webhook] %s on pitchdecks → syncing pitchdeck %s", event_type, pitchdeck_id)
    ok = await build_and_store_pitchdeck_embedding(pitchdeck_id)

    return {
        "status"      : "synced" if ok else "failed",
        "pitchdeck_id": pitchdeck_id,
        "event"       : event_type,
    }