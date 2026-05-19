import hmac
import hashlib
import os
from fastapi import APIRouter, Request, HTTPException, Header
from app.core.logger import get_logger

router = APIRouter()
logger = get_logger("GitHubWebhook")

def verify_signature(payload: bytes, signature: str) -> bool:
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "").encode()
    expected = "sha256=" + hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

@router.post("/webhook")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(...),
    x_hub_signature_256: str = Header(...),
):
    payload = await request.body()

    if not verify_signature(payload, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    data = await request.json()
    repo = data.get("repository", {}).get("full_name", "unknown")

    if x_github_event == "push":
        branch = data.get("ref", "").replace("refs/heads/", "")
        commit = data.get("head_commit", {}).get("id", "")[:7]
        logger.info(f"Push to {repo} branch={branch} commit={commit}")
        # Trigger any internal logic here, e.g. cache invalidation

    elif x_github_event == "deployment":
        logger.info(f"Deployment event on {repo}")

    elif x_github_event == "ping":
        logger.info(f"GitHub App connected successfully to {repo}")

    return {"status": "received", "event": x_github_event}