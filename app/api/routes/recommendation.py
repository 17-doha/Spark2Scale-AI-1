import time
import os
import uuid
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

# --- Import Logger ---
from app.utils.logger import logger

# --- Import Recommendation Logic ---
from app.graph.recommendation_agent.workflow import run_recommendation_agent
from app.core.config import Config
from app.graph.feed_recommedation_agent.tools import get_investor_subtags

router = APIRouter()

# In-memory job store, same pattern Evaluation + Market Research already use.
JOBS: dict = {}

class RecommendationInput(BaseModel):
    raw_input: Dict[str, Any]  # The original startup data
    evaluation_output: Dict[str, Any]  # The output from the evaluation agent
    request_id: Optional[str] = None
    startup_id: Optional[str] = None  # Supabase startup id; enables DB-sourced insights


def _run_recommendation_sync(input_data: RecommendationInput, api_key: str) -> dict:
    """Shared workflow runner, called from both sync and background paths."""
    return run_recommendation_agent(
        raw_input=input_data.raw_input,
        eval_output=input_data.evaluation_output,
        api_key=api_key,
        save_output=True,
        request_id=input_data.request_id,
        startup_id=input_data.startup_id,
    )


def _run_recommendation_task(job_id: str, input_data: RecommendationInput, api_key: str) -> None:
    """Background worker; writes status + result into JOBS."""
    start = time.time()
    try:
        logger.info(f"[JOB {job_id}] Recommendation starting")
        result = _run_recommendation_sync(input_data, api_key)
        duration = time.time() - start
        logger.info(f"[JOB {job_id}] Recommendation completed in {duration:.2f}s")
        JOBS[job_id] = {
            "status": "completed",
            "result": result,
            "duration": f"{duration:.2f}s",
        }
    except Exception as e:
        logger.error(f"[JOB {job_id}] Recommendation FAILED: {e}")
        JOBS[job_id] = {"status": "failed", "error": str(e)}


@router.post("/recommend")
async def get_recommendations(input_data: RecommendationInput):
    """
    Synchronous Recommendation entry point — kept for direct callers (Swagger,
    backward compatibility). Times out at Azure App Service's 230s gateway
    limit for cold workflows; prefer /recommend/start + /recommend/status for
    anything user-facing.
    """
    start_time = time.time()
    logger.info(f"[LAUNCH] Recommendation Agent triggered for Request ID: {input_data.request_id}")

    # Ensure API Key is present
    api_key = Config.GEMINI_API_KEY
    if not api_key:
        logger.error("[ERROR] GEMINI_API_KEY is missing in configuration.")
        raise HTTPException(status_code=500, detail="Gemini API Key not configured.")

    try:
        result = _run_recommendation_sync(input_data, api_key)
        duration = time.time() - start_time
        logger.info(f"[SUCCESS] Recommendation workflow finished in {duration:.2f}s")
        return result

    except Exception as e:
        logger.error(f"[ERROR] Recommendation Agent Failed: {str(e)}")
        if "validation error" in str(e).lower():
            raise HTTPException(status_code=422, detail=f"Data Schema Mismatch: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recommend/start")
async def start_recommend(input_data: RecommendationInput, background_tasks: BackgroundTasks):
    """
    Kick off recommendation generation in a background task and return a job
    id immediately. Caller then polls /recommend/status/{job_id}. Avoids Azure
    App Service's 230s front-door timeout because each HTTP call returns in
    under a second.
    """
    api_key = Config.GEMINI_API_KEY
    if not api_key:
        raise HTTPException(status_code=500, detail="Gemini API Key not configured.")

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "running"}
    background_tasks.add_task(_run_recommendation_task, job_id, input_data, api_key)
    return {"job_id": job_id, "status": "accepted"}


@router.get("/recommend/status/{job_id}")
async def recommend_status(job_id: str):
    """Polling endpoint. Mirrors /evaluate/status/{job_id} and /research/status/{job_id}."""
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job ID not found")
    return job



@router.get("/investors/{user_id}/subtags", response_model=List[str])
async def get_investor_interest_subtags(user_id: str):
    """
    Endpoint to fetch only the sub-tag names an investor is interested in
    based on the Neo4j graph.
    """
    logger.info(f"[GET] Fetching subtags for Investor ID: {user_id}")
    
    try:
        subtags = get_investor_subtags(user_id)
        
        if not subtags:
            # We return an empty list rather than a 404 to be safe 
            # (investor might exist but has no tag connections yet)
            logger.warning(f"[WARN] No subtags found for investor {user_id}")
            return []
            
        return subtags

    except Exception as e:
        logger.error(f"[ERROR] Failed to fetch subtags from Neo4j: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Graph Database Error")