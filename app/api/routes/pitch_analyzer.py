import os
import uuid
import sys
import subprocess
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from livekit.api import AccessToken, VideoGrants

router = APIRouter()

# Global reference to keep track of the background worker process
worker_process = None

@router.post("/start", summary="Start LiveKit AI Agent Worker")
async def start_agent_worker():
    """
    Spawns the background main.py worker that connects to LiveKit and listens for rooms.
    This ensures that the Azure Web App / Deployment runs the worker on-demand.
    """
    global worker_process
    
    # Check if thread/process is already running to prevent duplicates
    if worker_process is not None and worker_process.poll() is None:
        return {"status": "already_running", "pid": worker_process.pid, "message": "Worker is already active and listening."}
        
    # Build path to the agent script
    script_path = os.path.join(os.getcwd(), "app", "graph", "pitch_analyzer", "main.py")
    if not os.path.exists(script_path):
        raise HTTPException(status_code=500, detail=f"Agent script not found at {script_path}")
        
    env = os.environ.copy()
    
    # Start the worker in the background securely logging output
    log_file = open(os.path.join(os.getcwd(), "agent_worker.log"), "w", encoding="utf-8")
    
    worker_process = subprocess.Popen(
        [sys.executable, script_path, "dev"],
        cwd=os.path.dirname(script_path),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT
    )
    
    return {"status": "started", "pid": worker_process.pid, "message": "LiveKit worker spawned successfully in the background."}


class TokenRequest(BaseModel):
    participant_name: Optional[str] = "Founder"
    room_name: Optional[str] = None

@router.post("/token", summary="Generate LiveKit Token for Pitch Analyzer")
async def generate_pitch_analyzer_token(request: TokenRequest):
    """
    NOTE: Because we migrated token generation to your C# .NET Backend, 
    this endpoint is strictly a backup and won't actively be used by your Next.js app anymore.
    """
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not api_key or not api_secret:
        raise HTTPException(
            status_code=500,
            detail="LIVEKIT_API_KEY or LIVEKIT_API_SECRET is not configured on the server."
        )

    room_name = request.room_name or f"pitch-session-{uuid.uuid4().hex[:8]}"
    participant_identity = f"user_{uuid.uuid4().hex[:4]}"

    grant = VideoGrants(
        room=room_name,
        room_join=True,
        can_publish=True,
        can_publish_data=True,
        can_subscribe=True,
    )

    token = AccessToken(
        api_key=api_key,
        api_secret=api_secret,
    ).with_identity(participant_identity).with_name(request.participant_name).with_grants(grant)

    # Note: to_jwt() returns a string in livekit 0.8.0+
    jwt_token = token.to_jwt()

    return {
        "access_token": jwt_token,
        "room_name": room_name,
        "participant_identity": participant_identity
    }
