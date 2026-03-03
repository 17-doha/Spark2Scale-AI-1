from typing import TypedDict, Annotated, Dict, Any, List, Union
import operator

def replace_reducer(a, b):
    return b

class AgentState(TypedDict):
    # --- INPUT ---
    user_data: Dict[str, Any]
    
    # --- EXISTING OUTPUTS ---
    team_report: Annotated[Dict[str, Any], operator.ior]
    problem_report: Annotated[Dict[str, Any], replace_reducer]
    product_report: Annotated[Dict[str, Any], replace_reducer]
    
    # --- NEW AGENT OUTPUTS ---
    market_report: Annotated[Dict[str, Any], replace_reducer]
    traction_report: Annotated[Dict[str, Any], replace_reducer]
    gtm_report: Annotated[Dict[str, Any], replace_reducer]
    business_report: Annotated[Dict[str, Any], replace_reducer]
    vision_report: Annotated[Dict[str, Any], replace_reducer]
    operations_report: Annotated[Dict[str, Any], replace_reducer]

    # --- INTERMEDIATE ARTIFACTS ---
    search_results: Annotated[Dict[str, Any], operator.ior]
    
    # Product Fan-Out Specifics
    tech_stack: Annotated[Dict[str, Any], operator.ior]
    visual_analysis: Annotated[str, replace_reducer]
    product_contradiction: Annotated[str, replace_reducer]
    product_risk_report: Annotated[str, replace_reducer]
    
    # Shared Validation
    missing_report: Annotated[List[str], operator.add]
    
    # Optional: Plan from Planner Node
    plan: Annotated[Dict[str, Any], replace_reducer]

    final_report: Annotated[Dict[str, Any], replace_reducer]

    # --- T5-3B MODEL OUTPUT ---
    t5_deep_insight: Annotated[str, replace_reducer]
