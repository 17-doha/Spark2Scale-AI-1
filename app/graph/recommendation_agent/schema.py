from pydantic import BaseModel
from typing import List, Dict, Any, Optional, TypedDict

class SectionScore(BaseModel):
    score: float
    description: str

class StartupScores(BaseModel):
    team: SectionScore
    problem: SectionScore
    product: SectionScore
    market: SectionScore
    traction: SectionScore
    gtm: SectionScore
    economics: SectionScore
    vision: SectionScore
    ops: SectionScore

class StartupData(BaseModel):
    stage: str
    company_context: str
    scores: StartupScores
    # Added intermediate fields for internal state tracking
    insights: Optional[Dict[str, Any]] = None
    matched_patterns: Optional[List[Dict[str, Any]]] = None
    refined_statements: Optional[Dict[str, Any]] = None
    market_signals: Optional[Dict[str, Any]] = None

class RecommendationState(TypedDict):
    insights: Optional[Dict[str, Any]]
    matched_patterns: Optional[List[Dict[str, Any]]]
    refined_statements: Optional[Dict[str, Any]]
    market_signals: Optional[Dict[str, Any]]
    final_report: Optional[str]
    output_paths: Optional[Dict[str, Any]]
