from typing import TypedDict, Optional, Dict, Any, List


class BMCState(TypedDict, total=False):
    idea_name: str
    idea_description: str
    region: Optional[str]

    market_research: Dict[str, Any]
    evaluation: Dict[str, Any]
    recommendation: Dict[str, Any]

    extracted_context: Dict[str, Any]
    business_model_canvas: Optional[Dict[str, List[str]]]
    errors: List[str]
