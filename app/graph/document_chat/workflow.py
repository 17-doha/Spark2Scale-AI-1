"""
workflow.py — Builds and compiles the document chat LangGraph StateGraph.

Graph topology:

    START
      │
      ▼
  parse_document_node   (parses file, sanitises PII, caps query)
      │
      ▼
  answer_query_node     (runs LangChain QA chain against the parsed context)
      │
      ▼
     END

Usage
-----
    from app.graph.document_chat.workflow import app

    result = app.invoke({
        "file_path": "/path/to/deck.pptx",
        "query": "What is the GTM strategy?",
        "provider": "gemini",
        "model_name": None,
    })
    print(result["answer"])
"""

from langgraph.graph import END, START, StateGraph

from app.graph.document_chat.node import answer_query_node, parse_document_node
from app.graph.document_chat.state import DocumentChatState


def create_document_chat_graph():
    """Build and compile the document chat StateGraph."""
    workflow = StateGraph(DocumentChatState)

    # --- Nodes ---
    workflow.add_node("parse_document_node", parse_document_node)
    workflow.add_node("answer_query_node", answer_query_node)

    # --- Edges (sequential pipeline) ---
    workflow.add_edge(START, "parse_document_node")
    workflow.add_edge("parse_document_node", "answer_query_node")
    workflow.add_edge("answer_query_node", END)

    return workflow.compile()


# Module-level compiled graph — import this in routes / tests
app = create_document_chat_graph()
