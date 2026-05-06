from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class IdeaCheckInput(BaseModel):
    idea: str
    problem: str
    region: Optional[str] = "Global"

class IdeaCheckOutput(BaseModel):
    # "verdict" is what analyze_pain_points_prompt actually asks the LLM to return.
    # Was wrongly named "validation_status" before — caused silent field loss.
    verdict: str                        # VALIDATED / MODERATE / WEAK / INSUFFICIENT_DATA
    pain_score: int
    pain_score_reasoning: str
    solution_fit_score: str             # High / Medium / Low
    solution_fit_reasoning: str
    reasoning: str                      # Overall assessment — was missing from old schema
    evidence_quality_notes: str
    key_queries_executed: Dict[str, List[str]]
