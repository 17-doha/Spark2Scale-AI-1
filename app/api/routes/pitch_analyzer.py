import os
import uuid
import sys
import subprocess
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from livekit.api import AccessToken, VideoGrants

from app.graph.pitch_analyzer.main import load_company_context, run_extraction

router = APIRouter()

worker_process = None

@router.post("/extract", summary="Run LLM Pre-flight Extraction")
def run_pitch_extraction():
    """
    Runs the LLM extraction pipeline separately from the worker.
    Call this when the user clicks on the pitchdeck, so it processes the documents
    in the background BEFORE they actually start the voice session.
    """
    try:
        
        # Load documents (currently hardcoded demo docs in main.py)
        docs = load_company_context()
        
        # Force skip=False so it guarantees the extraction runs and creates/updates the cache
        cheat_sheet, voice_prompt = run_extraction(docs, skip=False)
        
        return {"status": "success", "message": "Extraction finished and cache updated."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")

@router.post("/start", summary="Start LiveKit AI Agent Worker")
async def start_agent_worker():
    global worker_process
    
    if worker_process is not None and worker_process.poll() is None:
        return {"status": "already_running", "pid": worker_process.pid}
        
    script_path = os.path.join(os.getcwd(), "app", "graph", "pitch_analyzer", "main.py")
    if not os.path.exists(script_path):
        raise HTTPException(status_code=500, detail=f"Agent script not found at {script_path}")
        
    env = os.environ.copy()
    
    # Start the worker in the background securely logging output to BOTH a file and stdout
    log_file = open(os.path.join(os.getcwd(), "agent_worker.log"), "a", encoding="utf-8")
    
    worker_process = subprocess.Popen(
        [sys.executable, script_path, "dev", "--skip-extraction"],
        cwd=os.path.dirname(script_path),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT
    )
    
    return {"status": "started", "pid": worker_process.pid}

class TokenRequest(BaseModel):
    participant_name: Optional[str] = "Founder"
    room_name: Optional[str] = None

@router.post("/token", summary="Generate LiveKit Token for Pitch Analyzer")
async def generate_pitch_analyzer_token(request: TokenRequest):
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
