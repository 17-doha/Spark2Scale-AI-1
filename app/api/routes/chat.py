"""
Spark2Scale — Friendly Startup Data-Gathering Chat
====================================================
The AI's ONLY job in /chat is to have a warm, curious conversation that
helps founders articulate their idea — and to ask good follow-up questions
so startup_data gets richer over time.

It does NOT evaluate, score, or lecture. If the founder asks a direct
question the AI can answer it briefly and then steer back to learning more.

Two endpoints:
  POST /chat              → returns ai_reply (natural language only)
  POST /update-startup-data → returns updated_startup_data (silent delta merge)
"""

import re
import json
import logging
import copy
from typing import Dict, Any

from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional
from app.core.limiter import api_limiter
from app.core.llm import ModalCustomLLM

router = APIRouter()
logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════════════
#  LAYER 1 — Prompt-Injection Guard
# ════════════════════════════════════════════════════════════════════════

_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"ignore\s+(all\s+)?above\s+instructions",
        r"disregard\s+(all\s+)?(previous|above|prior)\s+instructions",
        r"forget\s+(all\s+)?(previous|your)\s+(instructions|rules|guidelines)",
        r"override\s+(your\s+)?(instructions|rules|system\s*prompt)",
        r"do\s+not\s+follow\s+(your|the)\s+(instructions|rules)",
        r"new\s+instructions\s*:",
        r"(show|reveal|display|print|output|repeat|tell\s+me)\s+(your\s+)?(system\s*prompt|instructions|rules|guidelines)",
        r"what\s+(are|is)\s+your\s+(system\s*prompt|instructions|rules)",
        r"(give|show)\s+me\s+(the\s+)?(source\s*code|code|backend|server\s*code)",
        r"\bDAN\s+mode\b",
        r"\bjailbreak\b",
        r"\bbypass\s+(safety|filter|restriction|content\s*policy)",
        r"act\s+as\s+an?\s+(unrestricted|unfiltered|uncensored)",
        r"pretend\s+(you\s+)?(are|have)\s+no\s+(rules|restrictions|limits)",
        r"you\s+are\s+now\s+(free|unrestricted|unfiltered)",
        r"\bapi[\s_-]?key\b",
        r"\bpassword\b",
        r"\bsecret[\s_-]?key\b",
        r"\baccess[\s_-]?token\b",
        r"\bprivate[\s_-]?key\b",
    ]
]

def is_prompt_injection(text: str) -> bool:
    return any(p.search(text) for p in _INJECTION_PATTERNS)


# ════════════════════════════════════════════════════════════════════════
#  LAYER 2 — System Prompts
# ════════════════════════════════════════════════════════════════════════

_CHAT_SYSTEM_PROMPT = """\
You are Spark, a warm and genuinely curious startup advisor on the Spark2Scale platform.

YOUR ONLY JOB IN THIS CONVERSATION:
Learn as much as possible about the founder's startup idea by asking great questions.
You are NOT here to evaluate, judge, score, or give long advice. You are here to LISTEN and DIG DEEPER.

YOUR PERSONALITY:
- Warm, encouraging, and genuinely interested — like a smart friend who loves startups.
- Concise. Never write paragraphs when a sentence will do.
- You celebrate what the founder shares before asking your next question.
- You ask ONE question at a time. Never fire multiple questions at once.

HOW TO RESPOND:
1. Briefly acknowledge or reflect back what the founder just said (1 sentence max).
2. Ask ONE natural follow-up question to learn something you don't know yet.
   Focus on the biggest gap in the startup_data below.

WHAT TO ASK ABOUT (in rough priority order, but follow the conversation naturally):
- What problem they're solving and who feels it most
- Who their target customer is (be specific — age, job, situation)
- How customers currently solve this problem today (without the startup)
- What makes their solution different from existing options
- How they plan to make money (business model)
- What traction or early signals they have (users, waitlist, revenue, feedback)
- Team background — why are THEY the right people to build this
- What market or geography they're focused on first

IF THE FOUNDER ASKS YOU A DIRECT QUESTION:
Answer it briefly and helpfully (2-3 sentences max), then pivot back with a question
about their startup. Do not give long lectures or unsolicited advice.

RULES:
- NEVER give a score, rating, verdict, or evaluation of any kind.
- NEVER say "great idea!" or be sycophantic — be genuinely warm instead.
- NEVER ask more than one question per message.
- NEVER repeat a question that's already been answered in the chat history.
- Keep responses under 80 words total.
- Output plain conversational text only. No bullet points, no markdown, no JSON.
"""

_EXTRACTION_SYSTEM_PROMPT = """\
You are a STARTUP DATA EXTRACTOR for the Spark2Scale platform.

RULES:
1. You are a silent JSON-processing engine. No greetings, no commentary.
2. Output MUST be valid JSON only — no markdown, no preamble.
3. Read the startup_data, chat_history, and latest user message.
4. Extract ANY new information revealed by the user that is missing or different in startup_data.
5. Return ONLY the changed fields (deltas) — not the full data.

CRITICAL NESTING RULE:
startup_data has this structure: "data" -> "startup_evaluation" -> subsection -> field.
Your data_updates MUST mirror this exact nesting. Always start with "data" then "startup_evaluation".

EXAMPLE — user says "we're targeting HR managers at mid-size companies":
{
  "data_updates": {
    "data": {
      "startup_evaluation": {
        "target_market": {
          "primary_customer": "HR managers at mid-size companies"
        }
      }
    }
  }
}

If nothing new was revealed, return: { "data_updates": {} }
Return ONLY the delta — never the full startup_data.
"""


# ════════════════════════════════════════════════════════════════════════
#  Core: call Modal (Gemma 3n)
# ════════════════════════════════════════════════════════════════════════

def call_modal(user_content: str, system_prompt: str, json_mode: bool = False) -> Dict[str, Any]:
    combined_prompt = f"{system_prompt}\n\n{user_content}"
    llm = ModalCustomLLM(temperature=0.3 if not json_mode else 0.1, json_mode=json_mode)
    raw: str = llm.invoke(combined_prompt)

    if json_mode:
        text = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e} | raw: {text[:200]}")
            return {"data_updates": {}}

    return {"ai_reply": raw.strip()}


# ════════════════════════════════════════════════════════════════════════
#  Request Models
# ════════════════════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    user_message: str
    chat_history: list
    startup_data: dict

class UpdateDataRequest(BaseModel):
    user_message: str = ""
    chat_history: list
    startup_data: dict


# ════════════════════════════════════════════════════════════════════════
#  Endpoint 1 — /chat  (conversation only, never modifies data)
# ════════════════════════════════════════════════════════════════════════

@router.post("/chat")
@api_limiter.limit("20/minute")
async def process_idea_chat(request: Request, payload: ChatRequest):
    """
    Friendly conversation endpoint.
    Returns a short natural-language reply + one follow-up question.
    Does NOT modify startup_data — that is handled by /update-startup-data.
    """
    if is_prompt_injection(payload.user_message):
        logger.warning(f"[BLOCKED] Injection attempt: {payload.user_message[:60]}")
        return {"ai_reply": "I didn't quite follow that — can you tell me more about your startup idea?"}

    # Give the model just enough context: what we know + what was said.
    # We deliberately keep startup_data compact here (keys only if large)
    # because the chat model only needs to know what's MISSING, not everything.
    user_content = (
        f"WHAT WE KNOW SO FAR (startup_data):\n{json.dumps(payload.startup_data, indent=2)}\n\n"
        f"CONVERSATION SO FAR:\n{json.dumps(payload.chat_history)}\n\n"
        f"FOUNDER JUST SAID:\n{payload.user_message}"
    )

    try:
        result = call_modal(user_content, _CHAT_SYSTEM_PROMPT, json_mode=False)
        return {"ai_reply": result.get("ai_reply", "Tell me more — what problem does your startup solve?")}
    except Exception as e:
        logger.error(f"[ERROR] Chat failed: {e}")
        return {"ai_reply": "I'm having a little trouble right now — can you tell me more about your idea?"}


# ════════════════════════════════════════════════════════════════════════
#  Endpoint 2 — /update-startup-data  (silent delta extraction)
# ════════════════════════════════════════════════════════════════════════

def deep_merge(target: dict, updates: dict) -> dict:
    for key, value in updates.items():
        if isinstance(value, dict) and key in target and isinstance(target[key], dict):
            deep_merge(target[key], value)
        else:
            target[key] = value
    return target


@router.post("/update-startup-data")
@api_limiter.limit("20/minute")
async def update_startup_data(request: Request, payload: UpdateDataRequest):
    """
    Silent data extraction endpoint.
    Call this after each chat turn to keep startup_data up to date.
    Returns the fully merged startup_data — the caller stores it.
    """
    user_content = (
        f"CURRENT STARTUP DATA:\n{json.dumps(payload.startup_data)}\n\n"
        f"FULL CHAT HISTORY:\n{json.dumps(payload.chat_history)}\n\n"
        + (f"LATEST MESSAGE:\n{payload.user_message}\n\n" if payload.user_message.strip() else "")
        + "Extract any new startup information revealed and return the delta as instructed."
    )

    try:
        result = call_modal(user_content, _EXTRACTION_SYSTEM_PROMPT, json_mode=True)
    except Exception as e:
        logger.error(f"[ERROR] Extraction failed: {e}")
        return {"updated_startup_data": payload.startup_data}

    updates = result.get("data_updates", {})
    if not updates:
        return {"updated_startup_data": payload.startup_data}

    try:
        merged = deep_merge(copy.deepcopy(payload.startup_data), updates)
        return {"updated_startup_data": merged}
    except Exception as e:
        logger.error(f"[ERROR] Merge failed: {e}")
        return {"updated_startup_data": payload.startup_data}