from typing import TypedDict, Optional, List, Dict, Any

class IdeaCheckState(TypedDict):
    # Fixed Inputs
    idea: str
    problem: str
    region: str
    
    # Intermediate State
    validation_queries: Dict[str, List[str]]
    search_evidence: str
    
    # Output State
    analysis_result: Dict[str, Any]
    error: Optional[str]
