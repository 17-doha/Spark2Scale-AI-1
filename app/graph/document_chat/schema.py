from pydantic import BaseModel


class DocumentQARequest(BaseModel):
    """Incoming request body for the document QA endpoint."""

    file_path: str
    query: str
    provider: str = "gemini"
    model_name: str | None = None
    # NEW: Accept a list of previous messages
    chat_history: list[dict] | None = None
    # The type of document being discussed (e.g. "bmc", "swot", "competitor_matrix")
    document_type: str | None = None


class DocumentQAResponse(BaseModel):
    """Successful response from the document QA endpoint."""

    status: str
    provider_used: str
    query: str
    answer: str


# ---------------------------------------------------------------------------
# Chat Summarizer schemas
# ---------------------------------------------------------------------------

class ChatMessageInput(BaseModel):
    """A single chat message (user or assistant)."""
    role: str   # "user" or "assistant"
    content: str


class ChatSummarizerRequest(BaseModel):
    """Request body for the chat summarizer endpoint."""
    messages: list[ChatMessageInput]


class ChatSummarizerResponse(BaseModel):
    """Response from the chat summarizer endpoint."""
    summary: dict  # { "document_changes": [...], "enhanced_at": "..." }
