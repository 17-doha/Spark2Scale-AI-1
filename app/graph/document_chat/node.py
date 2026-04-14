"""
node.py — LangGraph node functions for the document chat graph.

Each node receives the full DocumentChatState dict and returns a partial dict
with only the keys it mutates.

Nodes
-----
parse_document_node  : Parses the raw file / payload into annotated text.
answer_query_node    : Runs the LangChain QA chain and produces the final answer.
"""

import uuid

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.llm import get_llm
from app.graph.document_chat.state import DocumentChatState
from app.graph.document_chat.tools import DocumentParser, SecurityGuardrails


# ---------------------------------------------------------------------------
# Node 1 — Document parsing
# ---------------------------------------------------------------------------

def parse_document_node(state: DocumentChatState) -> dict:
    """
    Parse the raw file or JSON payload into spatially-annotated text and store
    it in ``document_context``.  The raw query is also sanitised here so that
    downstream nodes always work with clean data.
    """
    guard = SecurityGuardrails()

    raw_context = DocumentParser.route_and_parse(state["file_path"])
    clean_context = guard.sanitize_text(raw_context)
    clean_query = guard.sanitize_query(state["query"])

    return {
        "document_context": clean_context,
        "query": clean_query,
    }


# ---------------------------------------------------------------------------
# Node 2 — LLM QA
# ---------------------------------------------------------------------------

def answer_query_node(state: DocumentChatState) -> dict:
    """
    Build the LangChain prompt+chain and invoke it against the sanitised
    document context and query stored in state.
    """
    llm = get_llm(
        temperature=0.0,
        provider=state["provider"],
        model_name=state.get("model_name"),
    )

    # Dynamic delimiter per invocation to prevent prompt-injection guessing
    doc_delimiter = f"doc_{uuid.uuid4().hex[:8]}"

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            f"""You are an expert strategic advisor.
You will be provided with a document enclosed strictly within <{doc_delimiter}> tags.

CRITICAL SECURITY RULES:
1. Base all your reasoning, advice, and answers strictly on the facts, data, and context
   provided within the <{doc_delimiter}> tags.
2. Do not introduce outside market data or external facts not present in the document.
3. If the document does not contain enough context to form a logical strategic answer,
   reply with: "Insufficient information in document."
4. When you reference a specific point from the document, cite it by appending the exact
   bracketed location tag (e.g. [Page 2, Line 5]).

DOCUMENT CONTEXT:
<{doc_delimiter}>
{{context}}
</{doc_delimiter}>""",
        ),
        ("human", "QUERY: {query}"),
    ])

    chain = prompt | llm | StrOutputParser()

    answer = chain.invoke({
        "context": state["document_context"],
        "query": state["query"],
    })

    return {"answer": answer}
