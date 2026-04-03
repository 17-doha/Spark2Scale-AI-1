"""
app/api/routes/feed_recommedation.py
=====================================
Key change: both /similar-investors and /recommend now run tag-filtered
Qdrant searches via the LangGraph pipeline — no new endpoints.
"""

from fastapi import APIRouter, HTTPException, Request
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
from app.graph.feed_recommedation_agent.tools.pitchdeck_tools import (
    build_and_store_pitchdeck_embedding,
)
from app.graph.feed_recommedation_agent.tools.tag_tools import (
    fetch_investor_tags,
    get_investor_subtags,
)
from app.graph.feed_recommedation_agent.tools import (
    build_and_store_investor_embedding,
    build_investor_embedding,
)
from app.graph.feed_recommedation_agent.workflow import filtered_search_app
from app.core.qdrant_client import get_qdrant
from qdrant_client.models import Filter, FieldCondition, MatchAny
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
        logger.error("[similar-investors] Qdrant search failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    return SimilarInvestorsResponse(investor_id=investor_id, results=results, k=k)


# ════════════════════════════════════════════════════════════════════════════
#  RECOMMEND  — full filtered LangGraph pipeline
# ════════════════════════════════════════════════════════════════════════════

@router.get("/recommend/{investor_id}", response_model=RecommendedPitchdecksResponse)
@api_limiter.limit("60/minute")
async def recommend_pitchdecks(request: Request, investor_id: str, k: int = TOP_K):
    """
    Top-K pitchdeck recommendations for a given investor.

    Runs the full LangGraph:
      1. generate_filter_tags   — tag pre-filter list (mock → swap later)
      2. build_investor_vector  — investor's aggregated embedding
      3. filtered_vector_search — Qdrant ANN within the filtered subset only
      4. rerank_candidates      — Jina cross-encoder re-scores → top-K
      5. format_output          — final shaping
    """
    result = await filtered_search_app.ainvoke({
        "investor_id"    : investor_id,
        "filter_tags"    : [],
        "investor_vector": None,
        "candidates"     : [],
        "final_results"  : [],
        "errors"         : [],
    })

    final_results = result.get("final_results", [])
    errors        = result.get("errors", [])

    if not final_results and errors:
        raise HTTPException(status_code=404, detail=errors[0])

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