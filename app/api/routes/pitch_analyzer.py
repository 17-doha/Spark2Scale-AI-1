import os
import uuid
import sys
import json
import tempfile
import subprocess
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from livekit.api import AccessToken, VideoGrants

from app.core.auth import get_current_user
from app.graph.pitch_analyzer.main import load_company_context, run_extraction

router = APIRouter()

# ── SINGLE SOURCE OF TRUTH PATHS ──
# The worker (workflow.py) writes files to the temp directory.
# The FastAPI route must read from the SAME location.
_TEMP_DIR = Path(tempfile.gettempdir())
_STATE_PATH = _TEMP_DIR / "spark2scale_session_state.json"
_REPORT_PATH = _TEMP_DIR / "spark2scale_session_report.json"
# Context file: carries pitchdeckid across the extract → generate-report boundary.
_CONTEXT_PATH = _TEMP_DIR / "spark2scale_session_context.json"

AGENT_ENV_KEYS = [
    "GROQ_API_KEY", "DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY",
    "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "LIVEKIT_URL",
]


@router.get("/env-check", summary="Check Required Env Vars are Set")
async def env_check():
    present = [k for k in AGENT_ENV_KEYS if os.environ.get(k)]
    missing = [k for k in AGENT_ENV_KEYS if not os.environ.get(k)]
    return {
        "ok": len(missing) == 0,
        "present": present,
        "missing": missing,
        "cwd": os.getcwd(),
    }


@router.get("/get-report", summary="Retrieve Last Generated Report")
async def get_report(pitchdeckid: Optional[str] = None, current_user=Depends(get_current_user)):
    """
    Returns the last generated report.
    If pitchdeckid is provided, tries to fetch session_report from Supabase first.
    Falls back to the local temp file if Supabase lookup fails or isn't available.
    """
    # ── Supabase-first path (when pitchdeckid is provided) ──────────────────
    if pitchdeckid:
        try:
            from app.core.supabase_client import supabase  # type: ignore
            if supabase is not None:
                result = (
                    supabase
                    .table("pitchdecks")
                    .select("session_report")
                    .eq("pitchdeckid", pitchdeckid)
                    .single()
                    .execute()
                )
                if result.data and result.data.get("session_report"):
                    return JSONResponse(content=result.data["session_report"])
        except Exception as e:
            import logging as _log
            _log.warning(f"[GET-REPORT] Supabase lookup failed, falling back to file: {e}")

    # ── Local file fallback ─────────────────────────────────────────────────
    if not _REPORT_PATH.exists():
        raise HTTPException(status_code=404, detail="No report found.")
    try:
        return json.loads(_REPORT_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        import logging as _log
        _log.error("[GET-REPORT] Failed to read report: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to read report.")


@router.post("/generate-report", summary="Build Investment Readiness Report")
async def generate_report_from_state(current_user=Depends(get_current_user)):
    """
    Builds the final report from the raw session state saved by the worker.
    Call this ALWAYS at the end of the session, whether it ended early or full time.
    """
    import asyncio as _asyncio
    import sys as _sys
    import logging as _log

    if not _STATE_PATH.exists():
        # If no state, check if a report already exists (e.g. from a previous run)
        if _REPORT_PATH.exists():
            return json.loads(_REPORT_PATH.read_text(encoding="utf-8"))
        raise HTTPException(
            status_code=404,
            detail="No session state or report found."
        )

    # Load saved state
    try:
        state_data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        _log.error("[GENERATE-REPORT] Failed to read session state: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to read session state.")

    # Import the report builder from the pitch_analyzer package
    try:
        _graph_path = str(Path(__file__).resolve().parents[2] / "graph" / "pitch_analyzer")
        if _graph_path not in _sys.path:
            _sys.path.insert(0, _graph_path)
        from tools import build_investment_readiness_report, detect_monotone  # type: ignore
    except ImportError as e:
        _log.error("[GENERATE-REPORT] Cannot import report builder: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Report builder unavailable.")

    # Monotone detection (fast, no LLM)
    feature_history = state_data.get("feature_history", [])
    mono_result = detect_monotone(feature_history)
    monotone_assessment = mono_result.get("assessment", "Not enough voice data.")

    # Build transcript
    transcript = state_data.get("full_transcript", "").strip()
    if not transcript:
        pitch_history = state_data.get("pitch_history", [])
        if pitch_history:
            transcript = " ".join(pitch_history)
            _log.warning("[GENERATE-REPORT] full_transcript empty — using pitch_history as fallback.")
        else:
            _log.warning("[GENERATE-REPORT] No speech captured at all — passing dummy transcript.")
            transcript = "The founder ended the session very early and practically no speech was recorded."

    # Build the report (LLM call — runs in FastAPI main process, no kill risk)
    try:
        loop = _asyncio.get_event_loop()
        report = await loop.run_in_executor(
            None,
            build_investment_readiness_report,
            state_data.get("session_log", []),
            state_data.get("grammar_buffer", []),
            state_data.get("structured_claims", {}),
            state_data.get("pitch_history", []),
            state_data.get("diligence_answered", []),
            transcript,
            monotone_assessment,
        )
    except Exception as e:
        _log.error("[GENERATE-REPORT] Report generation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Report generation failed. Please try again.")

    if not report:
        raise HTTPException(status_code=500, detail="LLM returned an empty report. Please try again.")

    # Save the generated report to disk for subsequent fast fetches
    try:
        _REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

    # ── Save to Supabase if we have a pitchdeckid from the context file ──────
    supabase_linked = False
    try:
        if _CONTEXT_PATH.exists():
            ctx = json.loads(_CONTEXT_PATH.read_text(encoding="utf-8"))
            pitchdeckid = ctx.get("pitchdeckid")
            if pitchdeckid:
                from app.graph.pitch_analyzer.supabase_report import save_report_to_supabase
                supabase_linked = save_report_to_supabase(pitchdeckid, report)
    except Exception as _ctx_err:
        import logging as _log
        _log.warning(f"[GENERATE-REPORT] Supabase save failed: {_ctx_err}")

    report["_supabase_linked"] = supabase_linked

    # Cleanup: remove state + context files so the next session starts clean
    try:
        _STATE_PATH.unlink(missing_ok=True)
        _CONTEXT_PATH.unlink(missing_ok=True)
    except Exception:
        pass

    return JSONResponse(content=report)


import threading
import logging as _logging
from collections import deque

worker_process = None
_worker_log: deque = deque(maxlen=200)   # O(1) append/pop, thread-safe for reads


def _stream_output(proc: subprocess.Popen) -> None:
    """
    Reads the worker subprocess stdout line-by-line and:
      1. Forwards every line to the parent Python logger (appears in Azure log stream)
      2. Keeps the last 200 lines in memory for diagnostics (deque — O(1) ops)
    """
    try:
        for raw in proc.stdout:                       # type: ignore[union-attr]
            line = raw.rstrip("\n")
            _worker_log.append(line)                  # deque handles maxlen automatically
            _logging.info("[AGENT] %s", line)
    except Exception:
        pass


class ExtractRequest(BaseModel):
    """Optional context IDs passed from the frontend to link this session to a pitch deck row."""
    pitchdeckid: Optional[str] = None
    startup_id: Optional[str] = None


@router.post("/extract", summary="Run LLM Pre-flight Extraction")
def run_pitch_extraction(request: ExtractRequest = Body(default=ExtractRequest()), current_user=Depends(get_current_user)):
    """
    Runs the LLM extraction pipeline separately from the worker.
    Call this when the user clicks on the pitchdeck, so it processes the documents
    in the background BEFORE they actually start the voice session.

    Accepts an optional JSON body with {pitchdeckid, startup_id} to link the
    upcoming session to a specific pitch deck row in Supabase. These IDs are
    persisted to spark2scale_session_context.json and read back by /generate-report.

    Skips the LLM call if a valid cache already exists (fast path — returns in <1s).
    """
    # ── Persist context IDs for use in /generate-report ────────────────────
    try:
        context = {
            "pitchdeckid": request.pitchdeckid,
            "startup_id":  request.startup_id,
        }
        _CONTEXT_PATH.write_text(json.dumps(context), encoding="utf-8")
        _logging.info(
            f"[EXTRACT] Session context saved — pitchdeckid={request.pitchdeckid}, "
            f"startup_id={request.startup_id}"
        )
    except Exception as _ctx_err:
        _logging.warning(f"[EXTRACT] Could not save session context: {_ctx_err}")

    try:
        docs = load_company_context(startup_id=request.startup_id)
        # skip=True → check Supabase cache first (keyed by startup_id), then local file.
        # Cache miss → full LLM extraction → result saved back to startups.cheat_sheet.
        cheat_sheet, voice_prompt = run_extraction(
            docs,
            skip=True,
            startup_id=request.startup_id,
        )
        source = "cache" if not docs else "llm"
        return {
            "status": "success",
            "source": source,
            "message": "Extraction finished and cache ready.",
            "pitchdeckid": request.pitchdeckid,
        }
    except Exception as e:
        import logging as _log
        _log.error("[EXTRACT] Extraction failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Extraction failed. Please try again.")


@router.post("/start", summary="Start LiveKit AI Agent Worker")
async def start_agent_worker(current_user=Depends(get_current_user)):
    global worker_process, _worker_log
    import asyncio as _asyncio

    # --- Already running? Return immediately ---
    if worker_process is not None and worker_process.poll() is None:
        return {"status": "already_running", "pid": worker_process.pid}

    script_path = os.path.join(os.getcwd(), "app", "graph", "pitch_analyzer", "main.py")
    if not os.path.exists(script_path):
        raise HTTPException(status_code=500, detail="Agent script not found.")

    env = os.environ.copy()
    _worker_log.clear()

    # --- Verify env vars BEFORE spawning (surface the error clearly) ---
    required_keys = ["GROQ_API_KEY", "DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY",
                     "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "LIVEKIT_URL"]
    missing = [k for k in required_keys if not env.get(k)]
    if missing:
        _logging.error("[AGENT START] Missing required env vars: %s", missing)
        raise HTTPException(status_code=500, detail="Agent worker cannot start due to missing configuration.")

    # --- Spawn subprocess with PIPE stdout so we can forward to Azure log stream ---
    _logging.info("[AGENT START] Spawning LiveKit agent worker from %s", script_path)
    worker_process = subprocess.Popen(
        [sys.executable, script_path, "dev", "--skip-extraction"],
        cwd=os.getcwd(),          # project root — .env and cache resolve here
        env=env,
        stdout=subprocess.PIPE,   # ← PIPE so we can read and forward to parent stdout
        stderr=subprocess.STDOUT, # merge stderr into stdout
        text=True,
        bufsize=1,                # line-buffered
    )

    # Spin up a daemon thread to forward subprocess logs to Azure's log stream
    t = threading.Thread(target=_stream_output, args=(worker_process,), daemon=True)
    t.start()

    # Give it 3 seconds to detect a crash-on-startup (missing keys, import error, etc.)
    await _asyncio.sleep(3)
    exit_code = worker_process.poll()
    if exit_code is not None:
        _logging.error("[AGENT START] Worker crashed at startup (exit %s)", exit_code)
        raise HTTPException(status_code=500, detail=f"Agent worker crashed at startup (exit {exit_code}).")

    _logging.info("[AGENT START] Worker is alive — pid=%s", worker_process.pid)
    # active_pitch_sessions.inc()
    return {"status": "started", "pid": worker_process.pid}


@router.get("/worker-status", summary="Check if AI Worker is Running")
async def get_worker_status(current_user=Depends(get_current_user)):
    """Returns whether the Python AI worker subprocess is currently alive."""
    global worker_process
    if worker_process is None:
        return {"running": False, "reason": "never_started"}
    code = worker_process.poll()
    if code is None:
        return {"running": True, "pid": worker_process.pid}
    return {"running": False, "reason": f"exited_with_code_{code}"}


@router.post("/stop", summary="Gracefully Stop the AI Agent Worker")
async def stop_agent_worker(current_user=Depends(get_current_user)):
    """
    Terminates the LiveKit worker subprocess.
    Call this from the frontend on 'End Session' or 'End Call' AFTER
    the room disconnect, so no zombie agent hangs around for the next session.

    The worker's on_participant_disconnected handler already:
      1. Sets state.phase='done'  → stops all background tasks
      2. Generates the offline report
      3. Calls ctx.room.disconnect() → agent leaves the LiveKit room

    This /stop endpoint then kills the worker OS process so the NEXT
    /start call spawns a completely fresh process with clean state.
    """
    global worker_process, _worker_log
    import asyncio as _asyncio

    if worker_process is None or worker_process.poll() is not None:
        worker_process = None
        return {"status": "not_running"}

    pid = worker_process.pid
    _logging.info("[AGENT STOP] Terminating worker pid=%s", pid)

    try:
        worker_process.terminate()
        # Give it up to 10s to exit cleanly (report may still be writing)
        for _ in range(20):
            await _asyncio.sleep(0.5)
            if worker_process.poll() is not None:
                break
        else:
            # Force-kill if still alive after 10s
            _logging.warning("[AGENT STOP] Process did not exit cleanly — force-killing pid=%s", pid)
            worker_process.kill()
    except Exception as e:
        _logging.warning("[AGENT STOP] Error during termination: %s", e)
    finally:
        worker_process = None
        _worker_log.clear()

    # active_pitch_sessions.dec()
    return {"status": "stopped", "pid": pid}


class TokenRequest(BaseModel):
    participant_name: Optional[str] = "Founder"
    room_name: Optional[str] = None

@router.post("/token", summary="Generate LiveKit Token for Pitch Analyzer")
async def generate_pitch_analyzer_token(request: TokenRequest, current_user=Depends(get_current_user)):

    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not api_key or not api_secret:
        raise HTTPException(status_code=500, detail="LIVEKIT_API_KEY missing")

    room_name = request.room_name or f"pitch-session-{uuid.uuid4().hex[:8]}"
    participant_identity = f"user_{uuid.uuid4().hex[:4]}"

    grant = VideoGrants(
        room=room_name,
        room_join=True,
        can_publish=True,
        can_publish_data=True,
        can_subscribe=True,
    )

    token = AccessToken(api_key=api_key, api_secret=api_secret).with_identity(participant_identity).with_name(request.participant_name).with_grants(grant)

    return {
        "access_token": token.to_jwt(),
        "room_name": room_name,
        "participant_identity": participant_identity
    }
