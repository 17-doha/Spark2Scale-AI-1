from pydantic import BaseModel


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
