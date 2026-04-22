from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class IdeaCheckInput(BaseModel):
    idea: str
    problem: str
    region: Optional[str] = "Global"

class IdeaCheckOutput(BaseModel):
    validation_status: str
    pain_score: int
    pain_score_reasoning: str
    solution_fit_score: str
    solution_fit_reasoning: str
    evidence_quality_notes: str
    key_queries_executed: Dict[str, List[str]]
