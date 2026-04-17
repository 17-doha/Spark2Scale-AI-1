from pydantic import BaseModel, Field
from typing import List


class BusinessModelCanvas(BaseModel):
    value_proposition: List[str] = Field(default_factory=list)
    customer_segments: List[str] = Field(default_factory=list)
    revenue_streams: List[str] = Field(default_factory=list)
    channels: List[str] = Field(default_factory=list)
    customer_relationships: List[str] = Field(default_factory=list)
    key_resources: List[str] = Field(default_factory=list)
    key_activities: List[str] = Field(default_factory=list)
    key_partnerships: List[str] = Field(default_factory=list)
    cost_structure: List[str] = Field(default_factory=list)


class BMCEnvelope(BaseModel):
    business_model_canvas: BusinessModelCanvas
