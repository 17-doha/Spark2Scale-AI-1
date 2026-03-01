from typing import Optional, TypedDict, List
from .schema import PPTDraft, Critique

# # --- Agent State ---

class PPTGenerationState(TypedDict):
    """
    Represents the state of the PPT generation graph.
    """
    research_data: str
    logo_path: Optional[str]
    color_palette: Optional[List[str]]
    use_default_colors: bool
    draft: Optional[PPTDraft]
    critique: Optional[Critique]
    iteration: int
    ppt_path: Optional[str]
    mode: Optional[str] # "create" or "edit"
