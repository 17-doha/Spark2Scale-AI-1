"""
tools.py — All tools available to Alex during a live pitch session.

CHANGES IN THIS VERSION:
  FIX A — _get_fast_llm() now uses Qwen-Max (DashScope) instead of Groq llama-3.1-8b.
           Eliminates 429 rate-limit crashes and the LLM narrating its own tool calls.

  FIX B — Consistency check prompts tightened to "hard facts only".
           Only flags NUMBER-vs-NUMBER or undeniable FACT-vs-FACT contradictions.
           NOT flagging: clarifications, self-corrections, vague language,
           speech disfluencies, transcription noise, or aspirational statements.
           Rule: "If not 100% certain → contradiction=false."
"""

import os
import re
import logging
import urllib.request
import urllib.parse
import json as _json
from typing import List, Dict, Any

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from dotenv import load_dotenv

# ═══════════════════════════════════════════════════════════════════════════════
# LLM SINGLETON  (FIX A — Qwen-Max, not Groq)
# ═══════════════════════════════════════════════════════════════════════════════

_fast_llm = None

def _get_fast_llm():
    """
    Returns a singleton Qwen client for background analysis tools.
    Uses qwen-turbo which has a separate quota from the older qwen-max.
    """
    global _fast_llm
    if _fast_llm is None:
        load_dotenv()
        _fast_llm = ChatOpenAI(
            api_key=os.getenv("GROQ_API_KEY_1", ""),
            base_url="https://api.groq.com/openai/v1",
            model="llama-3.3-70b-versatile",
            model_kwargs={"response_format": {"type": "json_object"}}
        )
    return _fast_llm


# ── LanguageTool PUBLIC REST API (no Java required) ──────────────────────────
_LT_API_URL   = "https://api.languagetool.org/v2/check"
_LT_AVAILABLE = True   # set to False on first network failure


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CLAIM EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

def extract_claims(text: str) -> Dict[str, Any]:
    """
    Extracts structured claims from a transcript chunk using Qwen-Max.
    """
    _BLANK = {
        "traction":  {"users": None, "revenue": None, "growth": None},
        "ask":       {"amount": None, "valuation": None},
        "economics": {"cac": None, "ltv": None, "churn": None},
        "gtm":       {"channels": []},
        "moat":      {"claims": []},
        "raw_numbers": [],
    }
    if not text.strip():
        return _BLANK

    llm    = _get_fast_llm()
    parser = JsonOutputParser()
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are an expert VC analyst extracting factual claims from a startup pitch transcript snippet.\n"
         "Extract into this EXACT JSON structure:\n"
         "{{\n"
         '  "traction":  {{"users": "string or null", "revenue": "string or null", "growth": "string or null"}},\n'
         '  "ask":       {{"amount": "string or null", "valuation": "string or null"}},\n'
         '  "economics": {{"cac": "string or null", "ltv": "string or null", "churn": "string or null"}},\n'
         '  "gtm":       {{"channels": ["list of strings"]}},\n'
         '  "moat":      {{"claims": ["list of strings"]}}\n'
         "}}\n"
         "Only output valid JSON. If a value isn't explicitly stated, use null or []. "
         "Normalize numbers but keep units (e.g. '1M', '500k')."),
        ("human", "{text}"),
    ])
    try:
        chain = prompt | llm | parser
        res   = chain.invoke({"text": text})
        res["raw_numbers"] = []
        return res
    except Exception as e:
        logging.error(f"extract_claims LLM failed: {e}")
        return _BLANK


# ═══════════════════════════════════════════════════════════════════════════════
# 2. TRUTH GUARD
# ═══════════════════════════════════════════════════════════════════════════════

def check_consistency_logic(new_claim: str, pitch_history: List[str]) -> dict:
    """
    FIX B: Checks whether new_claim contradicts anything the founder said earlier.

    Hard-facts-only rules:
    - ONLY flag NUMBER-vs-NUMBER or undeniable FACT-vs-FACT contradictions.
    - NOT flagging: clarifications, self-corrections ("I mean..."),
      vague language, speech disfluencies, incomplete sentences,
      transcription noise, or aspirational/future statements.
    - Rule: If not 100% certain → contradiction=false.
    """
    _CLEAN = {
        "contradiction": False, "is_critical": False,
        "error_type": None, "evidence": [], "conflicting_claim": None,
        "recommended_interrupt": "", "detail": "No contradiction detected.",
    }
    if not new_claim.strip() or not pitch_history:
        return _CLEAN

    llm    = _get_fast_llm()
    parser = JsonOutputParser()
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are a strict VC fact-checker monitoring a LIVE startup pitch.\n"
         "Your ONLY job: detect HARD FACTUAL contradictions between the new claim and prior statements.\n\n"
         "WHAT YOU MUST FLAG:\n"
         "  - A specific number stated earlier now stated as a DIFFERENT number\n"
         "    (e.g. founder said '$5M revenue' earlier, now says '$0 revenue')\n"
         "  - An explicit fact stated as true earlier, now stated as false\n\n"
         "WHAT YOU MUST NOT FLAG:\n"
         "  - The founder clarifying or correcting themselves ('I mean...', 'what I meant was...')\n"
         "  - Vague language like 'growing fast', 'a lot of users' — these are not hard claims\n"
         "  - Speech disfluencies, filler words, incomplete sentences\n"
         "  - Anything that could be a transcription artifact or micaring\n"
         "  - Aspirational or future statements vs. current state\n"
         "  - Rounding differences (e.g. '500k' vs '$490,000')\n\n"
         "RULE: If you are not 100%% certain this is a real factual contradiction, return contradiction=false.\n\n"
         "Output EXACTLY this JSON and nothing else:\n"
         "{{\n"
         '  "contradiction": false,\n'
         '  "conflicting_claim": "",\n'
         '  "evidence": ["prior exact quote", "new exact quote"],\n'
         '  "recommended_interrupt": "Wait — earlier you said X, but now you said Y. Which is the real number?"\n'
         "}}\n\n"
         "Prior statements: {history}"),
        ("human", "New claim to check: {claim}"),
    ])
    try:
        chain           = prompt | llm | parser
        history_snippet = " | ".join(pitch_history[-8:]) if pitch_history else "None"
        res             = chain.invoke({"history": history_snippet, "claim": new_claim})
        if res.get("contradiction"):
            return {
                "contradiction": True, "is_critical": True,
                "error_type": "Self-Contradiction",
                "evidence": res.get("evidence", []),
                "conflicting_claim": res.get("conflicting_claim", ""),
                "recommended_interrupt": res.get(
                    "recommended_interrupt",
                    "Wait — you're contradicting yourself. Which number is correct?"
                ),
                "detail": "Hard factual self-contradiction detected.",
            }
    except Exception as e:
        logging.error(f"check_consistency_logic LLM failed: {e}")
    return _CLEAN


def verify_claims_vs_cheat_sheet(new_claim: str, cheat_sheet: dict) -> dict:
    """
    FIX B: Checks new_claim against the company cheat sheet.
    Same strict hard-facts-only rules — only clear number-vs-number conflicts.
    """
    _CLEAN = {
        "contradiction": False, "is_critical": False,
        "error_type": None, "evidence": [], "recommended_interrupt": "",
        "detail": "No document conflict detected.",
    }
    if not new_claim.strip() or not cheat_sheet:
        return _CLEAN

    llm    = _get_fast_llm()
    parser = JsonOutputParser()
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are a strict VC fact-checker comparing a founder's live claim to their own company documents.\n\n"
         "WHAT YOU MUST FLAG:\n"
         "  - A specific number the founder stated that directly contradicts the documents\n"
         "    (e.g. founder says '$5M revenue' but documents clearly show '$0 MRR')\n"
         "  - A fact stated as true that documents clearly show is false\n\n"
         "WHAT YOU MUST NOT FLAG:\n"
         "  - Vague claims like 'we are growing', 'big market' — not verifiable as hard numbers\n"
         "  - Future plans or aspirations\n"
         "  - Anything the documents don't clearly address\n"
         "  - Clarifications or self-corrections\n"
         "  - Rounding differences\n\n"
         "RULE: If the documents do not contain a CLEAR contradicting number or fact, return contradiction=false.\n\n"
         "Output EXACTLY this JSON and nothing else:\n"
         "{{\n"
         '  "contradiction": false,\n'
         '  "evidence": ["document exact quote", "founder exact quote"],\n'
         '  "recommended_interrupt": "Hold on — your documents show X, but you just said Y. Which is accurate?"\n'
         "}}\n\n"
         "Company Documents: {docs}"),
        ("human", "Founder's claim: {claim}"),
    ])
    try:
        chain        = prompt | llm | parser
        docs_snippet = str(cheat_sheet)[:1500]
        res          = chain.invoke({"docs": docs_snippet, "claim": new_claim})
        if res.get("contradiction"):
            return {
                "contradiction": True, "is_critical": True,
                "error_type": "Document Conflict",
                "evidence": res.get("evidence", []),
                "recommended_interrupt": res.get(
                    "recommended_interrupt",
                    "Hold on — your documents contradict what you just said. Which is accurate?"
                ),
                "detail": "Document-vs-claim hard factual conflict detected.",
            }
    except Exception as e:
        logging.error(f"verify_claims_vs_cheat_sheet LLM failed: {e}")
    return _CLEAN


def deep_search_verification(category: str, massive_docs: dict) -> dict:
    """
    RAG-style lookup: pulls ground truth from the pre-loaded Company Context.
    """
    content = massive_docs.get(category, "")
    if not content:
        return {"found": False, "ground_truth": "",
                "summary": "No data found for this category."}
    excerpt = content[:2000].strip()
    return {
        "found": True,
        "ground_truth": excerpt,
        "summary": f"Document '{category}' found ({len(content)} chars). Key excerpt: {excerpt[:300]}...",
    }


def execute_check_consistency(
    claim: str,
    pitch_history: List[str],
    cheat_sheet: dict,
    massive_docs: dict,
) -> dict:
    """
    Two-stage consistency check:
      Stage 1 — Self-contradiction against pitch_history
      Stage 2 — Document conflict against cheat_sheet (or massive_docs fallback)
    """
    _CLEAN = {
        "contradiction": False, "is_critical": False, "error_type": None,
        "stage": None, "evidence": [], "recommended_interrupt": "",
        "detail": "No contradiction detected.",
    }
    self_check = check_consistency_logic(claim, pitch_history)
    if self_check["contradiction"]:
        return {**self_check, "stage": "self"}

    context = cheat_sheet if cheat_sheet else massive_docs
    if context:
        doc_check = verify_claims_vs_cheat_sheet(claim, context)
        if doc_check["contradiction"]:
            return {**doc_check, "stage": "summary"}

    return _CLEAN


# ═══════════════════════════════════════════════════════════════════════════════
# 3. RUBRIC SCORING  (deterministic — no LLM call)
# ═══════════════════════════════════════════════════════════════════════════════

RUBRIC_WEIGHTS = {
    "clarity":          20,
    "traction_proof":   20,
    "market_wedge":     15,
    "gtm_credibility":  15,
    "unit_economics":   15,
    "ask_use_of_funds": 10,
    "consistency":       5,
}


def compute_rubric_scores(
    session_log: List[dict],
    grammar_buffer: List[dict],
    structured_claims: dict,
    pitch_history: List[str],
    diligence_answered: List[str],
) -> dict:
    scores = {k: v for k, v in RUBRIC_WEIGHTS.items()}

    grammar_interrupts = sum(1 for e in session_log if e.get("reason") == "grammar_and_fillers")
    filler_total       = sum(len(gb.get("issues", [])) for gb in grammar_buffer)
    scores["clarity"] -= min(grammar_interrupts * 3, 10)
    scores["clarity"] -= min(filler_total, 10)
    scores["clarity"]  = max(scores["clarity"], 0)

    traction    = structured_claims.get("traction", {})
    has_users   = bool(traction.get("users"))
    has_revenue = bool(traction.get("revenue"))
    has_growth  = bool(traction.get("growth"))
    scores["traction_proof"] = (has_users * 7) + (has_revenue * 7) + (has_growth * 6)

    moat       = structured_claims.get("moat", {})
    has_market = any("market" in c.lower() or "tam" in c.lower() for c in pitch_history)
    has_moat   = len(moat.get("claims", [])) > 0
    scores["market_wedge"] = (has_market * 8) + (has_moat * 7)

    channels = structured_claims.get("gtm", {}).get("channels", [])
    scores["gtm_credibility"] = min(len(channels) * 5, 15)

    economics = structured_claims.get("economics", {})
    scores["unit_economics"] = (
        bool(economics.get("cac")) * 5 +
        bool(economics.get("ltv")) * 5 +
        bool(economics.get("churn")) * 5
    )

    ask = structured_claims.get("ask", {})
    scores["ask_use_of_funds"] = 10 if ask.get("amount") else 0

    contradiction_count = sum(
        1 for e in session_log
        if e.get("reason") in ("internal_contradiction", "document_conflict",
                               "Self-Contradiction", "Document Conflict")
    )
    scores["consistency"] = max(5 - contradiction_count * 2, 0)

    total     = sum(scores.values())
    max_total = sum(RUBRIC_WEIGHTS.values())
    pct       = total / max_total

    if   pct >= 0.90: grade = "A"
    elif pct >= 0.80: grade = "B+"
    elif pct >= 0.70: grade = "B"
    elif pct >= 0.60: grade = "C+"
    elif pct >= 0.50: grade = "C"
    elif pct >= 0.35: grade = "D"
    else:             grade = "F"

    notes = {
        "clarity":          f"{grammar_interrupts} grammar interrupt(s), {filler_total} filler issue(s)",
        "traction_proof":   f"users={has_users}, revenue={has_revenue}, growth={has_growth}",
        "market_wedge":     f"market_mentioned={has_market}, moat_claims={len(moat.get('claims', []))}",
        "gtm_credibility":  f"channels mentioned: {channels}",
        "unit_economics":   f"cac={bool(economics.get('cac'))}, ltv={bool(economics.get('ltv'))}, churn={bool(economics.get('churn'))}",
        "ask_use_of_funds": f"ask amount mentioned: {bool(ask.get('amount'))}",
        "consistency":      f"{contradiction_count} contradiction interrupt(s)",
    }
    return {
        "scores": scores, "max": RUBRIC_WEIGHTS,
        "total": total, "max_total": max_total,
        "grade": grade, "notes": notes,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. REALITY MENTOR TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

INVESTOR_ESSENTIALS = [
    ("problem",        ["problem", "pain point", "challenge", "issue", "solve"]),
    ("solution",       ["solution", "product", "platform", "tool", "we built", "we created"]),
    ("market_size",    ["market", "tam", "billion", "million users", "addressable"]),
    ("traction",       ["users", "revenue", "customers", "growth", "mrr", "arr"]),
    ("team",           ["team", "founder", "co-founder", "experience", "background"]),
    ("ask",            ["raising", "seeking", "ask", "investment", "round", "pre-seed", "seed"]),
    ("use_of_funds",   ["use of funds", "spend", "allocate", "hire", "marketing", "r&d"]),
    ("business_model", ["revenue model", "monetize", "charge", "subscription", "saas", "per user"]),
]


def check_investor_essentials(full_transcript: str) -> dict:
    all_keys = [e[0] for e in INVESTOR_ESSENTIALS]
    if not full_transcript.strip():
        return {"covered": [], "missing": all_keys}

    llm    = _get_fast_llm()
    parser = JsonOutputParser()
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are an expert startup advisor reviewing a full pitch transcript.\n"
         "Determine which of these 8 investor essentials were explicitly covered, and which are missing:\n"
         "problem, solution, market_size, traction, team, ask, use_of_funds, business_model.\n"
         'Output EXACTLY this JSON: {{"covered": ["list"], "missing": ["list"]}}'),
        ("human", "TRANSCRIPT:\n{transcript}"),
    ])
    try:
        chain = prompt | llm | parser
        return chain.invoke({"transcript": full_transcript})
    except Exception as e:
        logging.error(f"check_investor_essentials LLM failed: {e}")
        return {"covered": [], "missing": all_keys}


def build_investment_readiness_report(
    session_log: List[dict],
    grammar_buffer: List[dict],
    structured_claims: dict,
    pitch_history: List[str],
    diligence_answered: List[str],
    full_transcript: str,
) -> dict:
    rubric = compute_rubric_scores(
        session_log, grammar_buffer, structured_claims,
        pitch_history, diligence_answered,
    )
    killer_moments = [
        {
            "timestamp_s": round(e.get("timestamp", 0), 1),
            "type":        e.get("reason", "unknown"),
            "detail":      e.get("detail", ""),
        }
        for e in session_log if e.get("event") == "interrupt"
    ]
    essentials   = check_investor_essentials(full_transcript)
    sorted_scores = sorted(
        rubric["scores"].items(),
        key=lambda x: x[1] / rubric["max"][x[0]],
        reverse=True,
    )
    strengths  = [k for k, _ in sorted_scores[:3]]
    weaknesses = [k for k, _ in sorted_scores[-3:]]
    return {
        "grade":     rubric["grade"],
        "score":     rubric["total"],
        "max_score": rubric["max_total"],
        "rubric": {
            k: {"score": rubric["scores"][k], "max": rubric["max"][k], "notes": rubric["notes"][k]}
            for k in rubric["scores"]
        },
        "strengths":            strengths,
        "critical_weaknesses":  weaknesses,
        "essentials_checklist": {"covered": essentials["covered"], "missing": essentials["missing"]},
        "investor_killer_moments": killer_moments[:5],
        "diligence_answered":      diligence_answered,
        "claim_record":            structured_claims,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. GRAMMAR CHECK  (LanguageTool REST API + Qwen-Max fallback)
# ═══════════════════════════════════════════════════════════════════════════════

_CRITICAL_RULE_IDS = {
    "MORFOLOGIK_RULE_EN_US",
    "EN_A_VS_AN",
    "AGREEMENT_SENT_START",
    "DOUBLE_NEGATION",
    "ENGLISH_WORD_REPEAT_RULE",
}


def execute_grammar_check(text: str) -> dict:
    """
    Runs LanguageTool en-US on the given text via the public REST API.
    Falls back to Qwen-Max if the API is unreachable.
    """
    global _LT_AVAILABLE
    issues: list = []

    if _LT_AVAILABLE and text.strip():
        try:
            payload = urllib.parse.urlencode(
                {"text": text, "language": "en-US"}
            ).encode("utf-8")
            req = urllib.request.Request(
                _LT_API_URL, data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = _json.loads(resp.read().decode("utf-8"))

            critical_issues = []
            for m in data.get("matches", []):
                rule_id = m.get("rule", {}).get("id", "")
                msg     = m.get("message", "")
                ctx     = m.get("context", {}).get("text", "")
                offset  = m.get("context", {}).get("offset", 0)
                snippet = ctx[max(0, offset - 10): offset + 30].strip()
                issue_str = f"{msg} (near: '{snippet}')"
                issues.append(issue_str)
                if rule_id in _CRITICAL_RULE_IDS:
                    critical_issues.append(issue_str)

            if critical_issues:
                top = critical_issues[:2]
                # Require 2+ critical hits OR 1 structural error (word repeat / double negation)
                # to avoid interrupting on isolated filler words like 'uh' or 'um'
                structural_rules = {"ENGLISH_WORD_REPEAT_RULE", "DOUBLE_NEGATION"}
                has_structural = any(
                    m.get("rule", {}).get("id", "") in structural_rules
                    for m in data.get("matches", [])
                )
                if len(critical_issues) >= 2 or has_structural:
                    return {
                        "is_critical":           True,
                        "issue_count":           len(issues),
                        "issues":                issues,
                        "recommended_interrupt": (
                            f"Hold on — take a breath. You said '{top[0][:60]}'. "
                            "Try that sentence again, clean and direct."
                        ),
                    }
        except Exception as e:
            _LT_AVAILABLE = False
            logging.warning(f"LanguageTool REST API unreachable — falling back to LLM. ({e})")

    if text.strip() and not _LT_AVAILABLE:
        llm    = _get_fast_llm()
        parser = JsonOutputParser()
        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are an English teacher evaluating a startup founder's pitch.\n"
             "Check for CRITICAL grammar errors only "
             "(wrong verb form, wrong tense, subject-verb disagreement, a/an error).\n"
             "Ignore filler words — those are handled separately.\n"
             'Output EXACTLY this JSON: {{"has_error": false, "issues": []}}'),
            ("human", "{text}"),
        ])
        try:
            chain  = prompt | llm | parser
            result = chain.invoke({"text": text})
            if result.get("has_error") and result.get("issues"):
                return {
                    "is_critical":           True,
                    "issue_count":           len(result["issues"]),
                    "issues":                result["issues"],
                    "recommended_interrupt": f"Hold on — grammar issue: {result['issues'][0]}",
                }
        except Exception as e:
            logging.error(f"LLM grammar check failed: {e}")

    return {"is_critical": False, "issue_count": 0, "issues": [], "recommended_interrupt": ""}


# ═══════════════════════════════════════════════════════════════════════════════
# 6. JSON SCHEMA DEFINITIONS  (Qwen Realtime WebSocket session.update)
# ═══════════════════════════════════════════════════════════════════════════════

def get_tools_definition() -> list:
    return [
        {
            "type": "function", "name": "check_grammar",
            "description": (
                "INTERRUPT TOOL — call after EVERY founder turn. "
                "Runs LanguageTool en-US grammar check. "
                "If is_critical is True, interrupt immediately using the recommended_interrupt text."
            ),
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string", "description": "The exact words the founder just spoke."}},
                "required": ["text"],
            },
        },
        {
            "type": "function", "name": "check_consistency",
            "description": (
                "INTERRUPT TOOL. Call whenever the founder states a specific number, "
                "traction metric, market size, team fact, or funding figure. "
                "If contradiction is True, interrupt immediately."
            ),
            "parameters": {
                "type": "object",
                "properties": {"claim": {"type": "string", "description": "The exact factual claim the founder just made."}},
                "required": ["claim"],
            },
        },
        {
            "type": "function", "name": "deep_search_verification",
            "description": (
                "INTERRUPT TOOL. Use when check_consistency missed a discrepancy. "
                "Searches raw Company Context documents for ground truth."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["evaluation", "market_research", "cap_table", "swot", "business_plan"],
                    },
                    "claimed_value": {"type": "string"},
                },
                "required": ["category", "claimed_value"],
            },
        },
        {
            "type": "function", "name": "check_investor_essentials",
            "description": "REALITY MENTOR TOOL. Check pitch coverage after 2+ minutes.",
            "parameters": {
                "type": "object",
                "properties": {"transcript_so_far": {"type": "string"}},
                "required": ["transcript_so_far"],
            },
        },
        {
            "type": "function", "name": "flag_technical_language",
            "description": "REALITY MENTOR TOOL. Call when founder uses technical jargon.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# 7. AUDIO ANALYSIS (Moved from audio_analysis.py)
# ═══════════════════════════════════════════════════════════════════════════════
import numpy as np

def compute_audio_features(pcm_bytes: bytes, rate: int = 24000) -> dict:
    """
    Returns a dict with:
        rms_energy         (float): Loudness. Higher = louder.
        zero_crossing_rate (float): Voice texture. High = shaky/harsh, Low = smooth.
        pitch_estimate_hz  (float): Fundamental frequency in Hz. 0.0 if silence.
    """
    if len(pcm_bytes) == 0:
        return {"rms_energy": 0.0, "zero_crossing_rate": 0.0, "pitch_estimate_hz": 0.0}

    samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    if len(samples) == 0:
        return {"rms_energy": 0.0, "zero_crossing_rate": 0.0, "pitch_estimate_hz": 0.0}

    rms = float(np.sqrt(np.mean(samples ** 2)))

    zero_crossings = np.sum(np.abs(np.diff(np.sign(samples)))) / 2
    zcr = float(zero_crossings / len(samples))

    pitch_hz = _estimate_pitch_autocorr(samples, rate)

    return {
        "rms_energy": rms,
        "zero_crossing_rate": zcr,
        "pitch_estimate_hz": pitch_hz,
    }

def _estimate_pitch_autocorr(samples: np.ndarray, rate: int) -> float:
    """
    Estimates fundamental frequency using normalized autocorrelation.
    Returns 0.0 if signal is too quiet or no clear pitch is found.
    Search range: 80–450 Hz (full human speaking voice range).
    """
    rms = np.sqrt(np.mean(samples ** 2))
    if rms < 0.01:
        return 0.0

    correlation = np.correlate(samples, samples, mode='full')
    correlation = correlation[len(correlation) // 2:]

    min_lag = int(rate / 450)
    max_lag = int(rate / 80)

    if max_lag >= len(correlation) or min_lag >= max_lag:
        return 0.0

    search_region = correlation[min_lag:max_lag]
    peak_lag = int(np.argmax(search_region)) + min_lag

    if peak_lag == 0:
        return 0.0

    return float(rate / peak_lag)


class RMSCalibrator:
    """
    Measures a 5-second RMS baseline at pitch start and sets the inaudible threshold
    per-session, eliminating false positives caused by naturally quiet microphones.
    """

    CALIBRATION_FRAMES    = 100   # ~5s at 20 frames/s (50ms chunks)
    SCALE_FACTOR          = 0.25  # inaudible_threshold = median_rms * 0.25
    FLOOR                 = 0.002 # Never go below this (prevents threshold=0 edge case)
    CEILING               = 0.015 # Never go above this (sane upper bound)
    DEFAULT_THRESHOLD     = 0.004 # Fallback if calibration fails

    def __init__(self):
        self._samples: List[float] = []
        self.inaudible_threshold: float = self.DEFAULT_THRESHOLD
        self._calibrated = False

    def add_sample(self, rms: float):
        if not self._calibrated:
            self._samples.append(rms)
            if len(self._samples) >= self.CALIBRATION_FRAMES:
                self._compute()

    def _compute(self):
        arr = np.array(self._samples)
        # Only use non-silent frames for baseline (exclude near-zero values)
        active = arr[arr > 0.001]
        if len(active) < 10:
            # Room is nearly silent — use default
            self.inaudible_threshold = self.DEFAULT_THRESHOLD
        else:
            median_rms = float(np.median(active))
            raw = median_rms * self.SCALE_FACTOR
            self.inaudible_threshold = float(np.clip(raw, self.FLOOR, self.CEILING))
        self._calibrated = True

    def is_ready(self) -> bool:
        return self._calibrated

    def force_complete(self):
        """Call this if the pitch starts before calibration finishes (graceful fallback)."""
        if not self._calibrated:
            if self._samples:
                self._compute()
            else:
                self._calibrated = True


def detect_nervousness(feature_history: List[dict]) -> float:
    """
    Returns a 0.0–1.0 nervousness score based on:
      - ZCR variance (shaky voice texture)
      - Energy spike rate (stuttering / stopping-starting)
      - Pitch trend (rising pitch = increasing anxiety)
    """
    if len(feature_history) < 5:
        return 0.0

    zcr_values    = [f["zero_crossing_rate"] for f in feature_history]
    energy_values = [f["rms_energy"] for f in feature_history]
    pitch_values  = [f["pitch_estimate_hz"] for f in feature_history if f["pitch_estimate_hz"] > 0]

    score = 0.0

    zcr_std   = float(np.std(zcr_values))
    score    += 0.4 * min(zcr_std / 0.1, 1.0)

    spike_count = sum(
        1 for i in range(1, len(energy_values))
        if energy_values[i - 1] - energy_values[i] > 0.05
    )
    spike_rate = spike_count / max(len(energy_values) - 1, 1)
    score     += 0.4 * min(spike_rate / 0.5, 1.0)

    if len(pitch_values) >= 4:
        x     = np.arange(len(pitch_values), dtype=float)
        slope = float(np.polyfit(x, pitch_values, 1)[0])
        score += 0.2 * min(max(slope, 0.0) / 5.0, 1.0)

    return float(min(max(score, 0.0), 1.0))

HYSTERESIS_FRAMES = 14

def detect_acoustic_anomalies(
    feature_history: List[dict],
    inaudible_threshold: float = 0.004,
) -> dict | None:
    """
    Checks for extreme acoustic conditions using a hysteresis gate so single-frame
    spikes don't trigger false alerts.

    Returns a structured dict on anomaly:
        {
            "type": "acoustic",
            "reason": "inaudible" | "shouting" | "background_noise",
            "is_critical": True,
            "error_type": "Acoustic Anomaly",
            "evidence": ["avg_rms=0.001", "threshold=0.004"],
            "detail": "...",
            "recommended_interrupt": "..."
        }

    Returns None if no anomaly.
    """
    if len(feature_history) < HYSTERESIS_FRAMES:
        return None

    # Use the most recent HYSTERESIS_FRAMES frames for a stable reading
    recent  = feature_history[-HYSTERESIS_FRAMES:]
    avg_rms = float(np.mean([f["rms_energy"] for f in recent]))
    avg_zcr = float(np.mean([f["zero_crossing_rate"] for f in recent]))

    # ── Shouting / Clipping ────────────────────────────────────────────────────
    if avg_rms > 0.4:
        return {
            "type": "acoustic",
            "reason": "shouting",
            "is_critical": True,
            "error_type": "Acoustic Anomaly",
            "evidence": [f"avg_rms={avg_rms:.4f} > 0.4 (clipping threshold)"],
            "detail": "You are speaking far too loudly — the audio is clipping.",
            "recommended_interrupt": "You're clipping my mic. Speak at a normal volume."
        }

    # ── Background Hissing / Noise ─────────────────────────────────────────────
    if avg_zcr > 0.4 and avg_rms > 0.01:
        return {
            "type": "acoustic",
            "reason": "background_noise",
            "is_critical": True,
            "error_type": "Acoustic Anomaly",
            "evidence": [f"avg_zcr={avg_zcr:.4f} > 0.4", f"avg_rms={avg_rms:.4f}"],
            "detail": "There is heavy background noise obscuring your microphone.",
            "recommended_interrupt": "There's too much background noise. Move somewhere quieter."
        }

    # ── Inaudible (calibrated threshold + hysteresis) ─────────────────────────
    # Require non-zero ZCR so we don't fire when the mic is simply off
    if avg_rms < inaudible_threshold and avg_zcr > 0.02:
        return {
            "type": "acoustic",
            "reason": "inaudible",
            "is_critical": True,
            "error_type": "Acoustic Anomaly",
            "evidence": [
                f"avg_rms={avg_rms:.4f} < threshold={inaudible_threshold:.4f}",
                f"avg_zcr={avg_zcr:.4f}"
            ],
            "detail": "Your microphone volume is too low — you are inaudible.",
            "recommended_interrupt": "I can't hear you. Fix your mic or speak louder."
        }

    return None
# ═══════════════════════════════════════════════════════════════════════════════
# 7. MONOTONE DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

def detect_monotone(feature_history: List[dict]) -> dict:
    """
    Detects whether the founder spoke in a monotone voice throughout the pitch.

    Uses the std-dev of pitch_estimate_hz across all session frames:
      - Low variation (std-dev < 30 Hz) → monotone delivery
      - Medium variation (30–80 Hz)     → slightly flat but acceptable
      - High variation (> 80 Hz)        → good vocal variety

    Returns:
        {
            "is_monotone": bool,
            "variation_score": float,   # std-dev in Hz
            "assessment": str,          # human-readable verdict
        }
    """
    pitch_values = [
        f["pitch_estimate_hz"]
        for f in feature_history
        if f.get("pitch_estimate_hz", 0) > 0
    ]

    if len(pitch_values) < 10:
        return {
            "is_monotone": False,
            "variation_score": 0.0,
            "assessment": "Not enough voice data to assess vocal variety.",
        }

    std_dev = float(np.std(pitch_values))

    if std_dev < 30:
        return {
            "is_monotone": True,
            "variation_score": round(std_dev, 2),
            "assessment": (
                "Monotone delivery detected — very little pitch variation throughout your pitch. "
                "Investors struggle to stay engaged when the voice stays flat. "
                "Practice emphasizing key numbers and pausing before important statements."
            ),
        }
    elif std_dev < 80:
        return {
            "is_monotone": False,
            "variation_score": round(std_dev, 2),
            "assessment": (
                "Slightly flat delivery — some pitch variation, but could be more dynamic. "
                "Try emphasizing your problem statement and key metrics with a stronger vocal shift."
            ),
        }
    else:
        return {
            "is_monotone": False,
            "variation_score": round(std_dev, 2),
            "assessment": "Good vocal variety — your delivery was dynamic and engaging.",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 8. INVESTMENT READINESS REPORT BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def build_investment_readiness_report(
    session_log:        list,
    grammar_buffer:     list,
    structured_claims:  dict,
    pitch_history:      list,
    diligence_answered: list,
    full_transcript:    str,
    monotone_assessment: str = "",
) -> dict:
    """
    Builds a structured Investment Readiness Report from all session data.
    Called by the phase watcher at T=4:30 (pre-computation) and at T=5:00 (evaluating phase).
    """
    llm    = _get_fast_llm()
    parser = JsonOutputParser()

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are a senior VC analyst. Analyze this pitch session data and produce a JSON Investment Readiness Report. "
         "Be harsh, specific, and data-driven. Do not sugarcoat weaknesses.\n"
         "Output a JSON object with these fields:\n"
         "  grade: string (A/B+/B/C+/C/D/F)\n"
         "  score: integer (0-100)\n"
         "  max_score: 100\n"
         "  rubric: object with keys [team, problem, product, market, traction, financials, vision, communication, diligence] each having {{score: 0-10, notes: string}}\n"
         "  strengths: list of rubric keys that scored 7+\n"
         "  critical_weaknesses: list of rubric keys that scored below 5\n"
         "  essentials_checklist: {{covered: list, missing: list}} — from [problem, solution, market_size, traction, team, ask, business_model, moat]\n"
         "  investor_killer_moments: list of {{timestamp_s: number, type: string, detail: string}}\n"
         "  recommended_actions: list of 3 specific actions for the founder to take before the next pitch\n"
         "  final_verdict: string (one sentence — would you invest?)"
        ),
        ("human",
         "SESSION LOG (interrupts & events):\n{session_log}\n\n"
         "GRAMMAR ISSUES:\n{grammar_buffer}\n\n"
         "STRUCTURED CLAIMS EXTRACTED:\n{structured_claims}\n\n"
         "PITCH HISTORY (all founder statements):\n{pitch_history}\n\n"
         "DILIGENCE ANSWERS:\n{diligence_answered}\n\n"
         "FULL TRANSCRIPT:\n{full_transcript}\n\n"
         "VOCAL DELIVERY ASSESSMENT:\n{monotone_assessment}"
        ),
    ])

    chain = prompt | llm | parser

    try:
        result = chain.invoke({
            "session_log":        _json.dumps(session_log[-50:], ensure_ascii=False),
            "grammar_buffer":     _json.dumps(grammar_buffer[-20:], ensure_ascii=False),
            "structured_claims":  _json.dumps(structured_claims, ensure_ascii=False),
            "pitch_history":      " | ".join(pitch_history[-30:]),
            "diligence_answered": " | ".join(diligence_answered),
            "full_transcript":    full_transcript[-4000:],
            "monotone_assessment": monotone_assessment or "No vocal delivery data available.",
        })
        return result
    except Exception as e:
        logging.error(f"[REPORT] Failed to build investment readiness report: {e}")
        return {}
