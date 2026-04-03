"""
main.py — Entry point for the Spark2Scale AI Pitch Coach (Sparky).

Usage:
  python main.py                    # Full run: extract + voice session
  python main.py --skip-extraction  # Skip LLM extraction, use cached cheat sheet

Prerequisites:
  - .env file with DASHSCOPE_API_KEY=...
  - PyAudio working (microphone access required)
  - requirements.txt installed
"""

import os
import sys
import json
import asyncio
import logging
import argparse
from pathlib import Path
from dotenv import load_dotenv, find_dotenv

# Ensure the current directory is in sys.path so local imports work when imported as a module
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from workflow import build_extractor_workflow

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S"
)

load_dotenv(find_dotenv())
# ── Cache path for skipping re-extraction during development ─────────────────
CHEAT_SHEET_CACHE = Path("cheat_sheet_cache.json")

# ═══════════════════════════════════════════════════════════════════════════════
# STARTUP DOCUMENTS
# ═══════════════════════════════════════════════════════════════════════════════
# These are the 7 pre-loaded Company Context documents.
# In a production system, these would be loaded from a database or file upload.
# For the demo, they are hard-coded here as the ground truth for Sparky.

def load_company_context() -> dict:
    """Returns the 7 startup documents that form Sparky's Company Context."""
    return {
        # 1. Full evaluation report (scores across 9 dimensions)
        "evaluation": """{
            "team_report": {"score": "2.0/5", "explanation": "Lack of relevant experience and unclear roles."},
            "problem_report": {"score": "3.5/5", "explanation": "Clear problem statement, but impact unquantified."},
            "product_report": {"score": "1/5", "explanation": "Generic AI wrapper, no proprietary moat."},
            "market_report": {"score": "1/5", "explanation": "TAM claims are delusional, Red Ocean market."},
            "traction_report": {"score": "0/5", "explanation": "Zero users, zero revenue, zero signal."},
            "gtm_report": {"score": "1/5", "explanation": "Flawed strategy — TikTok Ads for Ministry of Education."},
            "business_report": {"score": "1/5", "explanation": "Freemium with no paid tier — charity project."},
            "vision_report": {"score": "2/5", "explanation": "Ambitious but vague, no clear beachhead."},
            "operations_report": {"score": "1/5", "explanation": "Ghost Ship: raising money with $0 burn."},
            "final_report": {
                "Weighted Score": 14.75,
                "Verdict": "Pass (Not Ready)",
                "Top 3 Priorities": [
                    "Fix the flawed GTM strategy.",
                    "Build a team with relevant experience.",
                    "Develop a unique, proprietary solution."
                ]
            }
        }""",

        # 2. Recommendations report
        "recommendations": """{
            "stage": "Pre-Seed",
            "company_context": "AI-driven startup evaluation platform for MENA founders.",
            "company_name": "Spark2Scale",
            "target_raise": "500k",
            "early_revenue": "0",
            "founder_experience": "Doha Hemdan (CEO) — AI Engineer at Tabaani; Salma Sherif (CTO) — AI Engineer at Praxilab; Mariam Elghandoor (COO) — ML Engineer; Sarah Elsayed (CFO) — Data Science student",
            "evaluation_scores": {
                "team": 4, "problem": 3, "product": 3, "market": 2,
                "traction": 1, "gtm": 2, "business": 2, "vision": 4, "ops": 3
            },
            "matched_patterns": [
                {"name": "Founder Avoids the Hard Job", "pattern_id": "FP-TEAM-001"},
                {"name": "Burn Without Milestones", "pattern_id": "FP-ECON-001"},
                {"name": "Vision Outruns Execution", "pattern_id": "FP-VISION-001"}
            ]
        }""",

        # 3. Market research data
        "market_research": """{
            "market_sizing": {
                "tam_value": "$44.1 Billion",
                "sam_value": "$22.1 Billion",
                "som_value": "$275.9 Million"
            },
            "validation": {
                "verdict": "MODERATE",
                "pain_score": 64.2,
                "confidence": "High"
            },
            "competitors": [
                "IdeaProof AI", "IdeaGlow", "Google Trends", "Ahrefs"
            ]
        }""",

        # 4. SWOT Analysis
        "swot": """{
            "strengths": [
                "Technical founding team with AI/ML backgrounds (Tabaani, Praxilab)",
                "Custom Transformer models tailored for MENA region"
            ],
            "weaknesses": [
                "Zero GTM or enterprise sales experience",
                "Pricing model is Freemium with no defined paid tier ($0 revenue)",
                "Stagnant velocity with 0 current users"
            ],
            "opportunities": [
                "Partnering with MENA incubators like Flat6Labs",
                "Expanding the Pitch Coach feature using Qwen3-Omni-Flash for live feedback"
            ],
            "threats": [
                "Generic AI models (ChatGPT/Claude) releasing specialized VC-agent wrappers",
                "Running out of runway due to $0 revenue and undefined acquisition strategy"
            ]
        }""",

        # 5. Business Plan
        "business_plan": """{
            "executive_summary": "Spark2Scale is an AI-driven startup evaluation platform for MENA founders.",
            "monetization": "Freemium model, no defined paid tier. Current MRR: $0.",
            "financials": {
                "current_mrr": 0,
                "monthly_burn_rate": "$100",
                "runway_months": 0,
                "target_raise": "$500,000"
            },
            "go_to_market": "TikTok Ads + word-of-mouth. Target: Ministry of Education and Cairo bookstores."
        }""",

        # 6. Cap Table
        "cap_table": """{
            "total_shares": 1000000,
            "shareholders": [
                {"name": "Doha Hemdan (CEO)",          "ownership_pct": 12.5},
                {"name": "Salma Sherif (CTO)",          "ownership_pct": 12.5},
                {"name": "Mariam Elghandoor (COO)",     "ownership_pct": 12.5},
                {"name": "Sarah Elsayed (CFO)",         "ownership_pct": 12.5},
                {"name": "External App Dev Agency",     "ownership_pct": 50.0}
            ],
            "notes": "Founders own only 50%. The remaining 50% was given to an agency for MVP development — RED FLAG."
        }""",

        # 7. Pitch Deck (PPT) slide content
        "ppt": """{
            "slide_1": "Title: Spark2Scale - The AI Co-Founder for MENA",
            "slide_2": "Problem: Founders lack a structured system to validate ideas.",
            "slide_3": "Solution: A multi-agent AI system that evaluates pitch decks.",
            "slide_4": "Market Size: $44.1 Billion Global Incubator Market.",
            "slide_5": "The Ask: Raising $500k Pre-Seed to scale engineering and launch TikTok marketing."
        }"""
    }


# ═══════════════════════════════════════════════════════════════════════════════
# EXTRACTION PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def run_extraction(docs: dict, skip: bool) -> tuple[dict, str]:
    """
    Runs the LangGraph extractor pipeline to compress the 7 docs into a VCCheatSheet.

    If --skip-extraction is passed AND a cache file exists, loads the cached result
    instead of calling the LLM — useful for faster iteration during development.

    Returns:
        (cheat_sheet_dict, voice_prompt_string)
    """
    if skip and CHEAT_SHEET_CACHE.exists():
        logging.info(f"Loading cheat sheet from cache: {CHEAT_SHEET_CACHE}")
        cached = json.loads(CHEAT_SHEET_CACHE.read_text(encoding="utf-8"))
        return cached["cheat_sheet"], cached["voice_prompt"]

    logging.info("Running Pre-Flight Extraction (this may take 30–60 seconds)...")
    extractor_app = build_extractor_workflow()
    
    # Needs a thread_id for MemorySaver checkpointing
    config = {"configurable": {"thread_id": "preflight_extraction"}}
    
    initial_state = {
        "raw_documents": docs,
        "cheat_sheet":   None,
        "voice_prompt":  None,
    }
    
    result = extractor_app.invoke(initial_state, config=config)

    cheat_sheet  = result.get("cheat_sheet", {})
    voice_prompt = result.get("voice_prompt", "")

    # Cache the result for future --skip-extraction runs
    CHEAT_SHEET_CACHE.write_text(
        json.dumps({"cheat_sheet": cheat_sheet, "voice_prompt": voice_prompt}, indent=2),
        encoding="utf-8"
    )
    logging.info(f"Cheat sheet cached to {CHEAT_SHEET_CACHE}")
    return cheat_sheet, voice_prompt


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Import LiveKit worker components
    from livekit.agents import WorkerOptions, cli
    from workflow import entrypoint, _PREFLIGHT

    # ── 1. Handle --skip-extraction before cli.run_app() sees sys.argv ─────────
    skip = "--skip-extraction" in sys.argv
    if skip:
        sys.argv.remove("--skip-extraction")

    # ── 2. Check required API keys ─────────────────────────────────────────────
    required = ["DASHSCOPE_API_KEY", "DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY"]
    missing  = [v for v in required if not os.environ.get(v)]
    if missing:
        logging.error(f"Missing required env vars: {', '.join(missing)}")
        sys.exit(1)

    # ── 3. Load Company Context + Run Extraction ───────────────────────────────
    logging.info("Loading Company Context documents...")
    docs = load_company_context()

    cheat_sheet, voice_prompt = run_extraction(docs, skip=skip)
    logging.info("VCCheatSheet ready. Starting LiveKit worker...")

    # ── 4. Populate the pre-flight cache for workflow.entrypoint() ────────
    _PREFLIGHT["cheat_sheet"]  = cheat_sheet
    _PREFLIGHT["massive_docs"] = docs
    _PREFLIGHT["voice_prompt"] = voice_prompt

    # ── 5. Launch LiveKit worker ──────────────────────────────────────────────
    if len(sys.argv) == 1:
        # If no subcommand provided, default to 'dev' so `python main.py` works
        sys.argv.append("dev")
        
    cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint
    ))

