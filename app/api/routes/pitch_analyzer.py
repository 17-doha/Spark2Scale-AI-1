import os
import uuid
import sys
import subprocess
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from livekit.api import AccessToken, VideoGrants

router = APIRouter()

worker_process = None

@router.post("/start", summary="Start LiveKit AI Agent Worker")
async def start_agent_worker():
    global worker_process
    
    if worker_process is not None and worker_process.poll() is None:
        return {"status": "already_running", "pid": worker_process.pid}
        
    script_path = os.path.join(os.getcwd(), "app", "graph", "pitch_analyzer", "main.py")
    if not os.path.exists(script_path):
        raise HTTPException(status_code=500, detail=f"Agent script not found at {script_path}")
        
    env = os.environ.copy()
    
    # Send worker output directly to the main system stdout so Azure catches it in Log Stream!
    worker_process = subprocess.Popen(
        [sys.executable, script_path, "dev"],
        cwd=os.path.dirname(script_path),
        env=env,
        stdout=sys.stdout,
        stderr=sys.stderr
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
