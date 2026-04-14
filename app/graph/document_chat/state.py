from typing import TypedDict


class DocumentChatState(TypedDict):
    """
    LangGraph state that flows through each node in the document chat graph.

    Fields
    ------
    file_path        : Raw input — a local file path OR a JSON string payload sent
                       directly from the frontend.
    query            : The user's natural-language question.
    provider         : LLM provider identifier (e.g. "gemini").
    model_name       : Optional model override (None → provider default).
    document_context : Parsed, spatially-annotated, PII-sanitised document text
                       produced by parse_document_node.
    answer           : Final LLM answer produced by answer_query_node.
    """

    file_path: str
    query: str
    provider: str
    model_name: str | None

    # --- intermediate / output ---
    document_context: str
    answer: str


class EnhanceState(TypedDict):
    """
    LangGraph state for the enhance graph.

    Fields
    ------
    startup_id              : The startup UUID (passed through for logging/context).
    document_type           : Human-readable document name (e.g. "Pitch Deck (PPT)").
    chat_history            : Full conversation so far as a list of role/content dicts.
    specific_edits          : Optional extra instructions typed by the founder.
    provider                : LLM provider identifier.
    model_name              : Optional model override.
    enhancement_instructions: Structured numbered list produced by enhance_node.
    """

    startup_id: str
    document_type: str
    chat_history: list[dict]
    specific_edits: str | None
    provider: str
    model_name: str | None

    # --- output ---
    enhancement_instructions: str
