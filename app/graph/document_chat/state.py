from typing import TypedDict


class DocumentChatState(TypedDict):
    """
    LangGraph state that flows through each node in the document chat graph.

    Fields
    ------
    file_path   : Raw input — a local file path OR a JSON string payload sent
                  directly from the frontend.
    query       : The user's natural-language question.
    provider    : LLM provider identifier (e.g. "gemini").
    model_name  : Optional model override (None → provider default).
    document_context : Parsed, spatially-annotated, PII-sanitised document text
                       produced by parse_document_node.
    answer      : Final LLM answer produced by answer_query_node.
    """

    file_path: str
    query: str
    provider: str
    model_name: str | None
    chat_history: list[dict] | None
    document_type: str | None  # e.g. "bmc", "swot", "competitor_matrix"

    document_context: str | None
    answer: str | None
