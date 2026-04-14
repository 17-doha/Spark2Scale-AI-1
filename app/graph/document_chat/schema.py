from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Document QA
# ---------------------------------------------------------------------------

class DocumentQARequest(BaseModel):
    """Incoming request body for the document QA endpoint."""

    file_path: str
    query: str
    provider: str = "gemini"
    model_name: str | None = None


class DocumentQAResponse(BaseModel):
    """Successful response from the document QA endpoint."""

    status: str
    provider_used: str
    query: str
    answer: str


# ---------------------------------------------------------------------------
# Enhance
# ---------------------------------------------------------------------------

class EnhanceRequest(BaseModel):
    """
    Request body for the /enhance endpoint.

    The caller sends the full chat history so the AI can understand
    what was discussed, plus an optional freeform string with any
    specific edits the founder wants applied before enhancing.
    """

    startup_id: str
    document_type: str                  # e.g. "Pitch Deck (PPT)", "SWOT Analysis"
    chat_history: list[dict]            # [{"role": "user"|"assistant", "content": "…"}]
    specific_edits: str | None = None   # optional founder instructions
    provider: str = "gemini"
    model_name: str | None = None


class EnhanceResponse(BaseModel):
    """
    Successful response from the /enhance endpoint.

    ``enhancement_instructions`` is a structured, bulleted description
    of exactly what should change in the document, ready to be consumed
    by the document generation / editing pipeline.
    """

    status: str
    document_type: str
    enhancement_instructions: str
