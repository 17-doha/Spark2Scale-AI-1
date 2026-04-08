import os
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from livekit.api import AccessToken, VideoGrants

router = APIRouter()

class TokenRequest(BaseModel):
    participant_name: Optional[str] = "Founder"
    room_name: Optional[str] = None

@router.post("/token", summary="Generate LiveKit Token for Pitch Analyzer")
async def generate_pitch_analyzer_token(request: TokenRequest):
    """
    Generates an AccessToken for the Pitch Analyzer LiveKit session.
    The client frontend uses this token to connect to the LiveKit server.
    """
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not api_key or not api_secret:
        raise HTTPException(
            status_code=500,
            detail="LIVEKIT_API_KEY or LIVEKIT_API_SECRET is not configured on the server."
        )

    # Use a specific room name if requested, otherwise generate one dynamically.
    # Usually we want a unique room ID per session so different users don't collide.
    room_name = request.room_name or f"pitch-session-{uuid.uuid4().hex[:8]}"

    # Provide identity name
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

    # Note: to_jwt() may return a string or bytes depending on the python JWT package version
    # It returns a string in livekit 0.8.0+
    jwt_token = token.to_jwt()

    return {
        "access_token": jwt_token,
        "room_name": room_name,
        "participant_identity": participant_identity
    }
