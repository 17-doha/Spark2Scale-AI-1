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
