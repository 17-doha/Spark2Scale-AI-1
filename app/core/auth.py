import os
from fastapi import HTTPException, Security, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.logger import get_logger

logger = get_logger(__name__)
_bearer = HTTPBearer()


def get_current_user(credentials: HTTPAuthorizationCredentials = Security(_bearer)):
    """Validate a Supabase-issued Bearer JWT. Returns the Supabase user object."""
    from app.core.supabase_client import supabase  # local import avoids circular dep
    if not supabase:
        raise HTTPException(status_code=503, detail="Authentication service unavailable.")
    try:
        result = supabase.auth.get_user(credentials.credentials)
        if not result or not result.user:
            raise HTTPException(status_code=401, detail="Invalid or expired token.")
        return result.user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")


def require_admin(x_admin_secret: str = Header(..., alias="X-Admin-Secret")):
    """Gate destructive admin endpoints behind a shared secret header."""
    secret = os.getenv("ADMIN_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="Admin access not configured.")
    if not (secret and x_admin_secret == secret):
        raise HTTPException(status_code=403, detail="Forbidden.")
