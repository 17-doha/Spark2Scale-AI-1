"""
workflow.py — Builds and compiles the document chat LangGraph StateGraphs.

Graphs
------
document_chat_app : START → parse_document_node → answer_query_node → END
enhance_app       : START → enhance_node → END

Usage
-----
    from app.graph.document_chat.workflow import document_chat_app, enhance_app

    # QA
    result = document_chat_app.invoke({
        "file_path": "/path/to/deck.pptx",
        "query": "What is the GTM strategy?",
        "provider": "gemini",
        "model_name": None,
    })
    print(result["answer"])

    # Enhance
    result = enhance_app.invoke({
        "startup_id": "abc-123",
        "document_type": "Pitch Deck (PPT)",
        "chat_history": [{"role": "user", "content": "The market slide is too vague."}],
        "specific_edits": "Also shorten the problem statement to 2 sentences.",
        "provider": "gemini",
        "model_name": None,
    })
    print(result["enhancement_instructions"])
"""

from langgraph.graph import END, START, StateGraph

from app.graph.document_chat.node import (
    answer_query_node,
    enhance_node,
    parse_document_node,
)
from app.graph.document_chat.state import DocumentChatState, EnhanceState


# ---------------------------------------------------------------------------
# Graph 1 — Document Q&A
# ---------------------------------------------------------------------------

def create_document_chat_graph():
    """Build and compile the document chat StateGraph."""
    workflow = StateGraph(DocumentChatState)

    workflow.add_node("parse_document_node", parse_document_node)
    workflow.add_node("answer_query_node", answer_query_node)

    workflow.add_edge(START, "parse_document_node")
    workflow.add_edge("parse_document_node", "answer_query_node")
    workflow.add_edge("answer_query_node", END)

    return workflow.compile()


# ---------------------------------------------------------------------------
# Graph 2 — Enhance
# ---------------------------------------------------------------------------

def create_enhance_graph():
    """Build and compile the document enhancement StateGraph."""
    workflow = StateGraph(EnhanceState)

    workflow.add_node("enhance_node", enhance_node)

    workflow.add_edge(START, "enhance_node")
    workflow.add_edge("enhance_node", END)

    return workflow.compile()


# Module-level compiled graphs — import these in routes / tests
document_chat_app = create_document_chat_graph()
enhance_app = create_enhance_graph()
