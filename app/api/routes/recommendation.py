import time
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

from app.utils.logger import logger
from app.graph.recommendation_agent.workflow import run_recommendation_agent
from app.core.config import Config
from app.core.auth import get_current_user
from app.graph.feed_recommedation_agent.tools import get_investor_subtags

router = APIRouter()

JOBS: dict = {}


class RecommendationInput(BaseModel):
    raw_input: Dict[str, Any]
    evaluation_output: Dict[str, Any]
    request_id: Optional[str] = None
    startup_id: Optional[str] = None  # Supabase startup id; enables DB-sourced insights


def _run_recommendation_sync(input_data: RecommendationInput, api_key: str) -> dict:
    return run_recommendation_agent(
        raw_input=input_data.raw_input,
        eval_output=input_data.evaluation_output,
        api_key=api_key,
        save_output=True,
        request_id=input_data.request_id,
        startup_id=input_data.startup_id,
    )


def _run_recommendation_task(job_id: str, input_data: RecommendationInput, api_key: str, owner_id: str) -> None:
    start = time.time()
    try:
        logger.info(f"[JOB {job_id}] Recommendation starting")
        result = _run_recommendation_sync(input_data, api_key)
        duration = time.time() - start
        logger.info(f"[JOB {job_id}] Recommendation completed in {duration:.2f}s")
        JOBS[job_id] = {"status": "completed", "result": result, "duration": f"{duration:.2f}s", "owner_id": owner_id}
    except Exception as e:
        logger.error(f"[JOB {job_id}] Recommendation FAILED: {e}", exc_info=True)
        JOBS[job_id] = {"status": "failed", "error": "Recommendation failed. Please try again.", "owner_id": owner_id}


@router.post("/recommend")
async def get_recommendations(input_data: RecommendationInput, current_user=Depends(get_current_user)):
    start_time = time.time()
    logger.info(f"[LAUNCH] Recommendation Agent triggered for Request ID: {input_data.request_id}")
    api_key = Config.GEMINI_API_KEY
    if not api_key:
        raise HTTPException(status_code=500, detail="Gemini API Key not configured.")
    try:
        result = _run_recommendation_sync(input_data, api_key)
        duration = time.time() - start_time
        logger.info(f"[SUCCESS] Recommendation workflow finished in {duration:.2f}s")
        return result
    except Exception as e:
        logger.error(f"[ERROR] Recommendation Agent Failed: {str(e)}", exc_info=True)
        if "validation error" in str(e).lower():
            raise HTTPException(status_code=422, detail="Input data schema mismatch.")
        raise HTTPException(status_code=500, detail="Recommendation failed. Please try again.")


@router.post("/recommend/start")
async def start_recommend(
    input_data: RecommendationInput,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
):
    api_key = Config.GEMINI_API_KEY
    if not api_key:
        raise HTTPException(status_code=500, detail="Gemini API Key not configured.")
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "running", "owner_id": current_user.id}
    background_tasks.add_task(_run_recommendation_task, job_id, input_data, api_key, current_user.id)
    return {"job_id": job_id, "status": "accepted"}


@router.get("/recommend/status/{job_id}")
async def recommend_status(job_id: str, current_user=Depends(get_current_user)):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job ID not found")
    if job.get("owner_id") != current_user.id:
        raise HTTPException(status_code=404, detail="Job ID not found")
    return {k: v for k, v in job.items() if k != "owner_id"}


@router.get("/investors/{user_id}/subtags", response_model=List[str])
async def get_investor_interest_subtags(user_id: str, current_user=Depends(get_current_user)):
    logger.info(f"[GET] Fetching subtags for Investor ID: {user_id}")
    try:
        subtags = get_investor_subtags(user_id)
        if not subtags:
            logger.warning(f"[WARN] No subtags found for investor {user_id}")
            return []
        return subtags
    except Exception as e:
        logger.error(f"[ERROR] Failed to fetch subtags from Neo4j: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Graph Database Error")
