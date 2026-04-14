"""
node.py — LangGraph node functions for the document chat graph.

Each node receives the full DocumentChatState dict and returns a partial dict
with only the keys it mutates.

Nodes
-----
parse_document_node  : Parses the raw file / payload into annotated text.
answer_query_node    : Runs the LangChain QA chain and produces the final answer.
enhance_node         : Reads chat history + optional edits and produces structured
                       enhancement instructions for the document.
"""

import uuid

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.llm import get_llm
from app.graph.document_chat.state import DocumentChatState, EnhanceState
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


# ---------------------------------------------------------------------------
# Node 3 — Enhance
# ---------------------------------------------------------------------------

def enhance_node(state: EnhanceState) -> dict:
    """
    Analyse the conversation history and any specific edits provided by the
    founder to produce a precise, structured list of enhancement instructions
    for the target document type.
    """
    llm = get_llm(
        temperature=0.2,
        provider=state["provider"],
        model_name=state.get("model_name"),
    )

    # ---- Build a readable transcript from the history ----
    transcript_lines: list[str] = []
    for msg in state.get("chat_history", []):
        role = str(msg.get("role", "unknown")).capitalize()
        content = str(msg.get("content", "")).strip()
        if content:
            transcript_lines.append(f"{role}: {content}")
    transcript = "\n".join(transcript_lines) if transcript_lines else "(no conversation history)"

    specific_edits_section = ""
    if state.get("specific_edits"):
        specific_edits_section = (
            f"\n\nFOUNDER'S SPECIFIC EDITS (apply these as well):\n{state['specific_edits']}"
        )

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """You are a strategic business document enhancement expert.
Your sole task is to analyse a conversation between a founder and an AI assistant
about their startup document, and produce a clear, structured, actionable list of
enhancement instructions that a document generation system can act on directly.

OUTPUT FORMAT (strict):
- Produce a numbered list of specific, concrete enhancement instructions.
- Each instruction must reference the exact element to change (e.g. "Executive Summary",
  "Slide 3 — Market Size", "Weaknesses section").
- Do NOT include vague guidance like "improve the tone". Be precise.
- Do NOT reproduce the conversation. Only produce the instructions list.
- Maximum 15 instructions.""",
        ),
        (
            "human",
            f"""Document type to enhance: {{document_type}}

Conversation history:
{{transcript}}{specific_edits_section}

Produce the numbered enhancement instructions list now:""",
        ),
    ])

    chain = prompt | llm | StrOutputParser()

    instructions = chain.invoke({
        "document_type": state["document_type"],
        "transcript": transcript,
    })

    return {"enhancement_instructions": instructions}
