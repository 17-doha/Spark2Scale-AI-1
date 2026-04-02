"""
State & Schema for the Feed Recommendation Agent.
"""
from typing import TypedDict, Optional, Annotated
import operator
from pydantic import BaseModel


# ── LangGraph State ──────────────────────────────────────────────────────────

class FeedRecommendationState(TypedDict):
    investor_id: str
    tags: list[str]
    embedding: Optional[list[float]]
    stored: bool
    similar_investors: list[dict]
    errors: Annotated[list[str], operator.add]


# ── Pydantic Request / Response ──────────────────────────────────────────────

class InvestorEmbeddingRequest(BaseModel):
    investor_id: str


class InvestorEmbeddingResponse(BaseModel):
    investor_id: str
    tags: list[str]
    stored: bool
    message: str


class SimilarInvestorsResponse(BaseModel):
    investor_id: str
    results: list[dict]       # [{"investor_id": "...", "similarity": 0.95}]
    k: int


class PitchdeckEmbeddingRequest(BaseModel):
    pitchdeck_id: str


class PitchdeckEmbeddingResponse(BaseModel):
    pitchdeck_id : str
    stored       : bool
    message      : str


class RecommendedPitchdecksResponse(BaseModel):
    investor_id : str
    results     : list[dict]
    k           : int