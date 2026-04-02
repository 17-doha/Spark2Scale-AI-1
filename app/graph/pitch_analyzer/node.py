"""
node.py — LangGraph node functions for the Pitch Coach agent workflow.

Nodes are pure functions: they receive an AgentState dict and return a partial dict
of only the fields they modify. LangGraph merges these back into state.

Nodes in this file:
  ── Extractor Pipeline ──
  - extract_vc_cheat_sheet   : Compresses 7 massive docs into a VCCheatSheet via LLM
  - format_voice_prompt      : Formats the cheat sheet into the Sparky system prompt

  ── Agent Runtime Nodes ──
  - tool_node                : Dispatches tool calls from the LLM; routes to correct function
  - phase_node               : Time-based phase transitions (listening → interrogating → evaluating)
"""

import os
import time
import logging
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from schema import VCCheatSheet
from state import PitchState, AgentState
from prompts import EXTRACTOR_SYSTEM_PROMPT, EXTRACTOR_HUMAN_PROMPT, build_cheat_sheet_prompt
import tools as tool_functions


# ═══════════════════════════════════════════════════════════════════════════════
# EXTRACTOR PIPELINE NODES
# ═══════════════════════════════════════════════════════════════════════════════

def extract_vc_cheat_sheet(state: PitchState) -> PitchState:
    """
    NODE 1: Compresses the 7 massive startup documents into a structured VCCheatSheet.
    Uses the Qwen-Max LLM via LangChain. Output is a dict matching the VCCheatSheet schema.
    """
    logging.info("--- NODE: COMPRESSING MASSIVE DOCUMENTS ---")
    docs = state["raw_documents"]

    llm = ChatOpenAI(
        api_key=os.getenv("GROQ_API_KEY_1"),
        base_url="https://api.groq.com/openai/v1",
        model="llama-3.3-70b-versatile"
    )

    parser = JsonOutputParser(pydantic_object=VCCheatSheet)
    prompt = ChatPromptTemplate.from_messages([
        ("system", EXTRACTOR_SYSTEM_PROMPT),
        ("human", EXTRACTOR_HUMAN_PROMPT)
    ])

    chain = prompt | llm | parser
    result = chain.invoke({
        "format_instructions": parser.get_format_instructions(),
        "evaluation":    docs.get("evaluation", "N/A"),
        "recommendations": docs.get("recommendations", "N/A"),
        "market_research": docs.get("market_research", "N/A"),
        "swot":          docs.get("swot", "N/A"),
        "business_plan": docs.get("business_plan", "N/A"),
        "cap_table":     docs.get("cap_table", "N/A"),
        "ppt":           docs.get("ppt", "N/A"),
    })
    return {"cheat_sheet": result}


def format_voice_prompt(state: PitchState) -> PitchState:
    """
    NODE 2: Formats the compressed VCCheatSheet dict into the Sparky system prompt string.
    This string is stored in state and injected into every session.update call.
    """
    logging.info("--- NODE: FORMATTING VOICE AGENT PROMPT ---")
    final_prompt = build_cheat_sheet_prompt(state["cheat_sheet"])
    return {"voice_prompt": final_prompt}


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT RUNTIME NODES
# ═══════════════════════════════════════════════════════════════════════════════

def tool_node(state: AgentState) -> dict:
    """
    Dispatches tool calls from the Realtime LLM to the correct Python function.

    The LLM sends a function_call event. The WebSocket handler wraps it as:
        active_tool_call = { "name": "...", "arguments": {...} }

    This node routes to the right function, captures the output, and:
      - For critical interrupt tools → logs to session_log
      - For grammar buffer tool     → appends to grammar_buffer
      - All tools                   → sets tool_output for the LLM to read

    Returns only the fields that changed.
    """
    call = state.get("active_tool_call", {})
    if not call:
        return {}

    name = call.get("name", "")
    args = call.get("arguments", {})
    current_time = state.get("time_elapsed", 0.0)

    output = ""
    new_log_entries = []

    # ── Grammar Check (LanguageTool API + regex fallback) ────────────────────
    if name == "check_grammar":
        text   = args.get("text", "")
        result = tool_functions.execute_grammar_check(text)
        if result["is_critical"]:
            issues_str = "; ".join(result["issues"][:2])
            logging.warning(f"[Grammar - CRITICAL via LT] {issues_str}")
            output = (
                f"CRITICAL INTERRUPT REQUIRED. LanguageTool found {result['issue_count']} grammar issue(s): {issues_str}. "
                f"SPEAK NOW: '{result['recommended_interrupt']}' Stop after."
            )
            new_log_entries.append({
                "event": "interrupt",
                "reason": "grammar_languagetool",
                "timestamp": current_time,
                "detail": issues_str,
            })
        else:
            output = f"Grammar OK (LanguageTool: {result['issue_count']} minor issues)."

    # ── Consistency Check (3-stage: self → summary → full docs) ──────────────
    elif name == "check_consistency":
        claim         = args.get("claim", "")
        history       = state.get("pitch_history", [])
        cheat_sheet   = state.get("structured_claims", {})
        massive_docs  = state.get("massive_docs", {})
        result = tool_functions.execute_check_consistency(claim, history, cheat_sheet, massive_docs)
        # Also update pitch_history with this claim
        new_history_entry = [claim]

        if result["contradiction"]:
            stage = result.get("stage", "unknown")
            logging.warning(f"[Consistency - {stage}] {result['detail']}")
            output = (
                f"CRITICAL INTERRUPT REQUIRED. Contradiction found (stage={stage}): {result['detail']}. "
                f"SPEAK NOW (1 sentence max): '{result['recommended_interrupt']}'"
            )
            new_log_entries.append({
                "event": "interrupt",
                "reason": result.get("error_type", "consistency"),
                "timestamp": current_time,
                "detail": result["detail"],
            })
        else:
            output = f"Consistent. Stage checked up to full docs. No contradiction for: '{claim[:60]}'"

        return {
            "tool_output": output,
            "pitch_history": new_history_entry,
            "active_tool_call": {},
            "session_log": new_log_entries,
        }

    # ── Legacy check_consistency (kept for backward compat) ──────────────────
    elif name == "check_consistency_legacy":
        claim = args.get("claim", "")
        history = state.get("pitch_history", [])
        result = tool_functions.check_consistency_logic(claim, history)
        output = str(result)
        new_history_entry = [claim]
        if result.get("contradiction"):
            new_log_entries.append({"event": "interrupt", "reason": "internal_contradiction", "timestamp": current_time, "detail": result.get("detail", "")})
        return {"tool_output": output, "pitch_history": new_history_entry, "active_tool_call": {}, "session_log": new_log_entries}

    # ── Critical Interrupt Tools ─────────────────────────────────────────────

    elif name == "deep_search_verification":
        result = tool_functions.deep_search_verification(
            category=args.get("category", ""),
            massive_docs=state.get("massive_docs", {})
        )
        output = str(result)
        # Log this event
        new_log_entries.append({
            "event": "tool_call",
            "tool": "deep_search_verification",
            "timestamp": current_time,
            "detail": f"Verified claim '{args.get('claimed_value', '')}' against '{args.get('category', '')}'"
        })

    else:
        output = f"Unknown tool: {name}"
        logging.warning(f"Unrecognized tool call: {name}")

    return {
        "tool_output": output,
        "session_log": new_log_entries,           # Accumulated via operator.add
        "active_tool_call": {},
    }


def phase_node(state: AgentState) -> dict:
    """
    Time-based phase transition logic.

    Timeline:
      0 – 180s  → "listening"      (founder pitches freely)
      180 – 300s → "interrogating" (Sparky asks diligence questions)
      300s+      → "evaluating"    (Sparky delivers full post-pitch review)

    Also checks:
      - If it's time to flush the grammar buffer (first pause detected externally)
      - If the nervousness score warrants a calming interrupt trigger

    Returns only fields that changed.
    """
    elapsed = state.get("time_elapsed", 0)
    current_phase = state.get("phase", "listening")
    new_phase = current_phase
    trigger = False

    if elapsed > 300 and current_phase != "evaluating":
        new_phase = "evaluating"
        trigger = True
        logging.info("Phase → EVALUATING (elapsed > 300s)")

    elif 180 < elapsed <= 300 and current_phase == "listening":
        new_phase = "interrogating"
        trigger = True
        logging.info("Phase → INTERROGATING (elapsed > 180s)")

    return {
        "phase": new_phase,
        "trigger_update": trigger,
    }