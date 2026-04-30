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
import time
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.core.llm import get_llm
from app.graph.document_chat.state import DocumentChatState
from app.graph.document_chat.tools import DocumentParser, SecurityGuardrails
from app.core.llm import get_llm, get_gemma_insight

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

# ---------------------------------------------------------------------------
# Node 2 — LLM QA
# ---------------------------------------------------------------------------

def answer_query_node(state: dict) -> dict:
    start_time = time.time()
    # ── Optional Gemma enrichment ──────────────────────────────────────────
    # If the provider is "gemma", route entirely to the finetuned model.
    # Otherwise, use it as an optional enrichment signal alongside the main LLM.
    if state.get("provider") == "gemma":
        answer = get_gemma_insight(
            context  = state.get("document_context", ""),
            question = state.get("query", ""),
            json_mode      = state.get("json_mode", False),
            temperature    = 1.0,
            max_new_tokens = 512,
        )
        inference_time = round(time.time() - start_time, 2)
        print(f"DEBUG - Node calculated time: {inference_time}") 
        return {"answer": answer, "inference_time": inference_time}

    # ── Standard LLM path (gemini / groq / ollama) ─────────────────────────
    llm = get_llm(
        temperature=0.2,
        provider=state["provider"],
        model_name=state.get("model_name"),
    )

    doc_delimiter = f"doc_{uuid.uuid4().hex[:8]}"

    # We use MessagesPlaceholder to inject the chat history dynamically
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            f"""You are an expert strategic advisor and startup mentor.
You are assisting a founder who is reviewing their startup document.

DOCUMENT CONTEXT:
<{doc_delimiter}>
{{context}}
</{doc_delimiter}>

CRITICAL RULES:
1. Try to answer the user's question using ONLY the provided document context. 
2. If you use the document, you MUST cite it using the bracketed location (e.g., [Page 2, Line 5]).
3. FALLBACK: If the answer is NOT in the document (or if the user is asking a general follow-up question or asking to explain a concept), rely on your expert startup knowledge.
4. If you use the FALLBACK mode, you MUST start your response with: "*(General Startup Knowledge)*\\n\\n" and DO NOT apologize or mention that the document doesn't contain the answer. Just answer the question directly.
5. Keep your answers concise, direct, and highly actionable. No fluff. Use bullet points if necessary. Do not use emojis in your fallback disclaimer."""
        ),
        MessagesPlaceholder(variable_name="chat_history"), # Inject memory here!
        ("human", "{query}"),
    ])

    chain = prompt | llm | StrOutputParser()

    # Format history if it exists in your state, otherwise pass empty list
    # Assuming your history is a list of dicts like [{"role": "user", "content": "..."}]
    raw_history = state.get("chat_history", [])
    formatted_history = []
    for msg in raw_history[-4:]: # Only grab the last 4 messages to save tokens
        if msg["role"] == "user":
            formatted_history.append(("human", msg["content"]))
        else:
            formatted_history.append(("assistant", msg["content"]))

    answer = chain.invoke({
        "context": state.get("document_context", ""),
        "chat_history": formatted_history,
        "query": state.get("query", ""),
    })

    inference_time = round(time.time() - start_time, 2)

    # Return the new metric in the state
    return {"answer": answer, "inference_time": inference_time}
