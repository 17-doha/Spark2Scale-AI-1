import os
import sys
import json
import asyncio
import logging
import argparse
import tempfile
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

# ── Local cache — dev fallback only (no startup_id available) ───────────────
_LOCAL_CHEAT_SHEET_CACHE = Path("cheat_sheet_cache.json")

# ── UNIFIED STATE PATH ────────────────────────────────────────────────────────
# This writes to the writable cloud directory. The report file has been removed.
_TEMP_DIR = Path(tempfile.gettempdir())
_SESSION_STATE_PATH = _TEMP_DIR / "session_state.json"
# ═══════════════════════════════════════════════════════════════════════════════
# STARTUP DOCUMENTS
# ═══════════════════════════════════════════════════════════════════════════════
# These are the 7 pre-loaded Company Context documents.
# In a production system, these would be loaded from a database or file upload.
# For the demo, they are hard-coded here as the ground truth for Sparky.

def load_company_context(startup_id: str = None) -> dict:
    """Returns the startup documents that form Sparky's Company Context from Supabase."""
    import tempfile
    
    _TEMP_DIR = Path(tempfile.gettempdir())
    _CONTEXT_PATH = _TEMP_DIR / "spark2scale_session_context.json"
    
    if not startup_id and _CONTEXT_PATH.exists():
        try:
            ctx = json.loads(_CONTEXT_PATH.read_text(encoding="utf-8"))
            startup_id = ctx.get("startup_id")
        except Exception as e:
            logging.warning(f"Could not read context file: {e}")
            
    if not startup_id:
        logging.warning("No startup_id provided or found in context, returning empty context.")
        return {}

    try:
        # Import the Supabase client from the core module.
        _project_root = str(Path(__file__).resolve().parents[3])
        if _project_root not in sys.path:
            sys.path.insert(0, _project_root)

        from app.core.supabase_client import supabase  # type: ignore

        if supabase is None:
            logging.warning("Supabase client not initialized.")
            return {}
        
        result = supabase.table("documents").select("type, json_response").eq("startup_id", startup_id).execute()
        
        docs = {}
        if result.data:
            for row in result.data:
                doc_type = row.get("type", "").lower()
                json_resp = row.get("json_response")
                
                if not json_resp:
                    continue
                    
                # Convert the json_response to a string since the existing LLM extractor expects strings.
                json_str = json.dumps(json_resp) if isinstance(json_resp, dict) else str(json_resp)
                
                if "founder evaluation" in doc_type or "evaluation" in doc_type:
                    docs["evaluation"] = json_str
                elif "recommendation" in doc_type:
                    docs["recommendations"] = json_str
                elif "market research" in doc_type:
                    docs["market_research"] = json_str
                elif "swot" in doc_type:
                    docs["swot"] = json_str
                elif "business plan" in doc_type or "bmc" in doc_type:
                    docs["business_plan"] = json_str
                elif "cap table" in doc_type:
                    docs["cap_table"] = json_str
                elif "ppt" in doc_type or "pitch deck" in doc_type:
                    docs["ppt"] = json_str
                elif "competitive analysis" in doc_type or "competitor matrix" in doc_type:
                    docs["competitive_analysis"] = json_str
                    
        return docs
    except Exception as e:
        logging.error(f"Failed to fetch from supabase: {e}")
        return {}


# ═══════════════════════════════════════════════════════════════════════════════
# EXTRACTION PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def _load_cheat_sheet_from_supabase(startup_id: str) -> tuple[dict, str] | None:
    """
    Tries to load a previously cached VCCheatSheet from startups.cheat_sheet in Supabase.
    Returns (cheat_sheet, voice_prompt) on cache hit, or None on miss/error.
    """
    try:
        _project_root = str(Path(__file__).resolve().parents[3])
        if _project_root not in sys.path:
            sys.path.insert(0, _project_root)
        from app.core.supabase_client import supabase  # type: ignore
        if supabase is None:
            return None
        result = supabase.table("startups").select("cheat_sheet").eq("sid", startup_id).single().execute()
        cached = result.data.get("cheat_sheet") if result.data else None
        if cached and cached.get("cheat_sheet") and cached.get("voice_prompt"):
            logging.info(f"[CACHE HIT] Loaded cheat_sheet from startups.cheat_sheet for startup_id={startup_id}")
            return cached["cheat_sheet"], cached["voice_prompt"]
    except Exception as e:
        logging.warning(f"[CACHE] Supabase cheat_sheet load failed: {e}")
    return None


def _save_cheat_sheet_to_supabase(startup_id: str, cheat_sheet: dict, voice_prompt: str) -> None:
    """
    Persists the VCCheatSheet to startups.cheat_sheet in Supabase so future
    sessions for the same startup skip the 30-60s LLM extraction step.
    """
    try:
        _project_root = str(Path(__file__).resolve().parents[3])
        if _project_root not in sys.path:
            sys.path.insert(0, _project_root)
        from app.core.supabase_client import supabase  # type: ignore
        if supabase is None:
            return
        payload = {"cheat_sheet": cheat_sheet, "voice_prompt": voice_prompt}
        supabase.table("startups").update({"cheat_sheet": payload}).eq("sid", startup_id).execute()
        logging.info(f"[CACHE] cheat_sheet saved to startups.cheat_sheet for startup_id={startup_id}")
    except Exception as e:
        logging.warning(f"[CACHE] Supabase cheat_sheet save failed: {e}")


def run_extraction(docs: dict, skip: bool, startup_id: str = None) -> tuple[dict, str]:
    """
    Runs the LangGraph extractor pipeline to compress startup docs into a VCCheatSheet.

    Cache strategy (fastest → slowest):
      1. Supabase startups.cheat_sheet  — persistent, per-startup, survives restarts.
      2. Local file _LOCAL_CHEAT_SHEET_CACHE — dev-only fallback (no startup_id).
      3. Full LLM extraction            — 30-60 seconds, result saved to both above.

    Args:
        docs:       Raw document dict from load_company_context().
        skip:       If True, attempt cache lookup before running the LLM.
        startup_id: UUID of the startup (used to key the Supabase cache).

    Returns:
        (cheat_sheet_dict, voice_prompt_string)
    """
    # ── 1. Supabase cache (per-startup, production path) ────────────────────
    if skip and startup_id:
        cached = _load_cheat_sheet_from_supabase(startup_id)
        if cached:
            return cached

    # ── 2. Local file cache (dev fallback when no startup_id) ────────────────
    if skip and not startup_id and _LOCAL_CHEAT_SHEET_CACHE.exists():
        logging.info(f"[CACHE HIT] Loading cheat sheet from local cache: {_LOCAL_CHEAT_SHEET_CACHE}")
        try:
            cached = json.loads(_LOCAL_CHEAT_SHEET_CACHE.read_text(encoding="utf-8"))
            if cached.get("cheat_sheet") and cached.get("voice_prompt"):
                return cached["cheat_sheet"], cached["voice_prompt"]
            logging.warning("[CACHE] Local cache file is empty/corrupt — re-running extraction.")
        except Exception as e:
            logging.warning(f"[CACHE] Failed to read local cache: {e} — re-running extraction.")

    # ── 3. Full LLM extraction ────────────────────────────────────────────────
    logging.info("Running Pre-Flight Extraction (this may take 30–60 seconds)...")
    extractor_app = build_extractor_workflow()
    config = {"configurable": {"thread_id": f"preflight_{startup_id or 'dev'}"}}
    initial_state = {
        "raw_documents": docs,
        "cheat_sheet":   None,
        "voice_prompt":  None,
    }
    result = extractor_app.invoke(initial_state, config=config)

    cheat_sheet  = result.get("cheat_sheet", {})
    voice_prompt = result.get("voice_prompt", "")

    # ── Persist to Supabase (production) ─────────────────────────────────────
    if startup_id:
        _save_cheat_sheet_to_supabase(startup_id, cheat_sheet, voice_prompt)

    # ── Persist to local file (dev fallback) ─────────────────────────────────
    try:
        _LOCAL_CHEAT_SHEET_CACHE.write_text(
            json.dumps({"cheat_sheet": cheat_sheet, "voice_prompt": voice_prompt}, indent=2),
            encoding="utf-8"
        )
        logging.info(f"[CACHE] Cheat sheet also saved locally to {_LOCAL_CHEAT_SHEET_CACHE}")
    except Exception as e:
        logging.warning(f"[CACHE] Could not write local cache: {e}")

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
    # DASHSCOPE_API_KEY: used by background tasks AND real-time voice session
    required = ["DASHSCOPE_API_KEY", "DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY"]
    missing  = [v for v in required if not os.environ.get(v)]
    if missing:
        logging.error(f"[STARTUP ABORT] Missing required env vars: {', '.join(missing)}")
        logging.error("The worker will NOT start. Add these keys to your .env file.")
        sys.exit(1)

    # ── 3. Load Company Context + Run Extraction ───────────────────────────────
    logging.info("Loading Company Context documents...")
    # Resolve startup_id from context file so the cache is keyed correctly
    _startup_id: str | None = None
    try:
        _ctx_path = Path(tempfile.gettempdir()) / "spark2scale_session_context.json"
        if _ctx_path.exists():
            _startup_id = json.loads(_ctx_path.read_text(encoding="utf-8")).get("startup_id")
    except Exception:
        pass
    docs = load_company_context(startup_id=_startup_id)

    cheat_sheet, voice_prompt = run_extraction(docs, skip=skip, startup_id=_startup_id)
    logging.info("VCCheatSheet ready. Starting LiveKit worker...")

    # ── 4. Populate the pre-flight cache for workflow.entrypoint() ────────
    _PREFLIGHT["cheat_sheet"]  = cheat_sheet
    _PREFLIGHT["massive_docs"] = docs
    _PREFLIGHT["voice_prompt"] = voice_prompt

    # ── 5. Launch LiveKit worker ──────────────────────────────────────────────
    if len(sys.argv) == 1:
        # If no subcommand provided, default to 'dev' so `python main.py` works
        sys.argv.append("dev")
        
    # ── Validate _PREFLIGHT before launching ──────────────────────────────────
    if not _PREFLIGHT.get("cheat_sheet"):
        logging.error("[STARTUP ABORT] _PREFLIGHT cheat_sheet is empty — agent will have no context!")
        sys.exit(1)

    logging.info(f"[STARTUP] _PREFLIGHT loaded: {len(str(_PREFLIGHT['cheat_sheet']))} chars in cheat_sheet.")

    cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint,
        # ── CRITICAL: Azure Docker cold-start needs extra time ────────────────
        # Default is ~10s. Our import chain (torch/silero, deepgram, livekit)
        # takes 7-9s in Docker — bumping to 60s eliminates the proc_pool
        # TimeoutError cascade seen in the Azure logs.
        initialize_process_timeout=60.0,
        # Keep 2 warm processes ready so a job is immediately served.
        # Setting to 1 is enough for single-user demo; increase for production.
        num_idle_processes=1,
    ))

