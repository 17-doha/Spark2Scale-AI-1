import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.core.llm import get_llm
from app.graph.document_chat.schema import ChatSummarizerRequest, ChatSummarizerResponse

logger = logging.getLogger(__name__)

router = APIRouter()

SYSTEM_PROMPT = (
    "You are a document improvement analyst for startup founders.\n\n"
    "You will receive a conversation between a user (founder) and an AI assistant about a startup document.\n"
    "Your job is to extract a clear, structured list of ALL the specific changes/improvements "
    "the user wants applied to their document.\n\n"
    "RULES:\n"
    "- Focus ONLY on concrete changes or improvements the user explicitly requested or implied they want.\n"
    "- Ignore greetings, filler text, or questions that are purely informational with no action item.\n"
    "- Each change should be a clear, actionable instruction "
    "(e.g. 'Add a market size section with TAM/SAM/SOM breakdown').\n"
    "- If the conversation contains no actionable document changes, return an empty list.\n\n"
    "IMPORTANT: You MUST respond with ONLY valid JSON. No markdown, no explanation. "
    "Example format: "
    '{"document_changes": ["Change 1 description", "Change 2 description"]}'
)


@router.post("/summarize", response_model=ChatSummarizerResponse)
async def summarize_chat(request: ChatSummarizerRequest):
    """
    Summarizes a list of chat messages to extract all document changes
    the user wants applied. Uses Gemini and returns a structured JSON result.
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages provided to summarize.")

    # Build conversation text
    conversation_text = "\n".join(
        f"{msg.role.upper()}: {msg.content}"
        for msg in request.messages
    )

    logger.info(f"[chat_summarizer] Summarizing {len(request.messages)} messages with Gemini.")

    raw_output = ""
    try:
        llm = get_llm(provider="groq", temperature=0.1)

        # Merge system instructions + conversation into ONE HumanMessage.
        # This avoids convert_system_message_to_human=True in ChatGoogleGenerativeAI
        # which would re-parse SystemMessage content through a LangChain template
        # and mistake {"document_changes"} in the prompt as a template variable.
        full_prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"Here is the conversation to analyze:\n\n{conversation_text}"
        )

        from langchain_core.messages import HumanMessage
        result = llm.invoke([HumanMessage(content=full_prompt)])
        raw_output = result.content if hasattr(result, "content") else str(result)

        # Strip accidental markdown fences
        cleaned = raw_output.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        parsed = json.loads(cleaned)

        if "document_changes" not in parsed:
            parsed = {"document_changes": []}

        summary = {
            "document_changes": parsed["document_changes"],
            "enhanced_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(f"[chat_summarizer] Extracted {len(summary['document_changes'])} changes.")
        return ChatSummarizerResponse(summary=summary)

    except json.JSONDecodeError as e:
        logger.error(
            f"[chat_summarizer] Failed to parse Gemini JSON: {e} | Raw: {raw_output!r}"
        )
        raise HTTPException(
            status_code=500,
            detail="AI returned an unparseable response. Please try again."
        )
    except Exception as e:
        logger.error(f"[chat_summarizer] Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Summarization failed. Please try again.")
