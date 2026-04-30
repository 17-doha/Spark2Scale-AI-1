from typing import Dict, Any, List, TypedDict, Annotated
from operator import add

class DocumentGeneratorState(TypedDict, total=False):
    """
    Represents the state of the document generator LangGraph workflow.
    `total=False` means keys are not strictly required if they start uninitialized.
    """
    # Inputs
    document_type: str # "swot" or "competitor_analysis"
    idea_name: str
    idea_description: str
    region: str
    market_research: Dict[str, Any]
    comment: str

    
    # Intermediate SWOT Data
    reviews_data: Dict[str, Any]
    gap_data: Dict[str, Any]
    barriers_data: Dict[str, Any]
    weaknesses_data: Dict[str, Any]
    tows_data: Dict[str, Any]
    
    # Fully assembled context for the final LLM prompt
    swot_context: Dict[str, Any]

    # Output Data
    swot_document: Dict[str, Any]
    competitor_analysis_document: Dict[str, Any]
    
    # Competitor Analysis Pipeline Variables
    competitor_names: List[str]
    competitors: List[Dict[str, Any]]
    
    # Errors
    errors: Annotated[List[str], add]
