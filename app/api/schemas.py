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
