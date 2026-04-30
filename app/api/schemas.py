from pydantic import BaseModel
from typing import Optional

class ResearchRequest(BaseModel):
    idea: str
    problem: str
    region: Optional[str] = None

class ResearchResponse(BaseModel):
    message: str
    pdf_path: Optional[str] = None
    json_path: Optional[str] = None
    data: Optional[dict] = None

class SWOTRequest(BaseModel):
    idea_name: str
    idea_description: str
    region: Optional[str] = "Global"
    market_research: dict

class SWOTResponse(BaseModel):
    message: str
    swot_document: Optional[dict] = None
    errors: Optional[list] = None

class CompetitorAnalysisRequest(BaseModel):
    idea_name: str
    idea_description: str
    region: Optional[str] = "Global"
    market_research: dict

class CompetitorAnalysisResponse(BaseModel):
    message: str
    competitor_analysis_document: Optional[dict] = None
    errors: Optional[list] = None

class BMCRequest(BaseModel):
    idea_name: str
    idea_description: str
    region: Optional[str] = "Global"
    market_research: dict
    evaluation: Optional[dict] = None
    recommendation: Optional[dict] = None

class BMCResponse(BaseModel):
    message: str
    business_model_canvas: Optional[dict] = None
    errors: Optional[list] = None


class BMCEnhanceRequest(BaseModel):
    """Request body for POST /api/v1/bmc/enhance.

    Refines an existing BMC using the founder's document change requests
    (typically produced by the chat-summarizer endpoint).
    """
    idea_name: str
    idea_description: str
    region: Optional[str] = "Global"
    current_bmc: dict              # The existing Business Model Canvas (9-block dict).
    document_changes: list[str]    # Ordered list of founder change requests.


class BMCEnhanceResponse(BaseModel):
    message: str
    business_model_canvas: Optional[dict] = None
    change_log: Optional[list[str]] = None   # Per-block summary of what was updated.
    errors: Optional[list] = None
