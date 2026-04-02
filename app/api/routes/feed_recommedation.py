from fastapi import APIRouter, HTTPException, Request
from app.core.limiter import api_limiter
from app.core.logger import get_logger
from app.graph.feed_recommedation_agent.schema import InvestorEmbeddingRequest, InvestorEmbeddingResponse, SimilarInvestorsResponse
from app.graph.feed_recommedation_agent.tools import fetch_investor_tags, build_and_store_investor_embedding, build_and_store_all, build_investor_embedding, get_top_k_similar_investors
import os

router = APIRouter()
logger = get_logger(__name__)
TOP_K = int(os.getenv("TOP_K", "10"))


@router.post("/investor-embedding", response_model=InvestorEmbeddingResponse)
@api_limiter.limit("30/minute")
async def upsert_investor_embedding(request: Request, payload: InvestorEmbeddingRequest):
    tags = fetch_investor_tags(payload.investor_id)
    if not tags:
        raise HTTPException(status_code=404, detail="Investor not found or has no tags.")
    ok = await build_and_store_investor_embedding(payload.investor_id)
    return InvestorEmbeddingResponse(
        investor_id=payload.investor_id,
        tags=tags,
        stored=ok,
        message="Stored." if ok else "Failed to store.",
    )


@router.post("/investor-embedding/batch")
@api_limiter.limit("5/minute")
async def upsert_all_investor_embeddings(request: Request):
    results = await build_and_store_all()
    success = sum(1 for v in results.values() if v)
    return {"total": len(results), "success": success, "failed": len(results) - success}


@router.get("/similar-investors/{investor_id}", response_model=SimilarInvestorsResponse)
@api_limiter.limit("60/minute")
async def get_similar_investors(request: Request, investor_id: str, k: int = TOP_K):
    vector = await build_investor_embedding(investor_id)
    if vector is None:
        raise HTTPException(status_code=404, detail="Investor has no tags.")
    return SimilarInvestorsResponse(investor_id=investor_id, results=get_top_k_similar_investors(vector, k=k), k=k)