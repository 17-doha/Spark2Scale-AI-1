from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from app.graph.market_research_agent.workflow import market_research_app
from app.graph.idea_check.workflow import idea_check_app
from app.api.schemas import ResearchRequest, ResearchResponse
from app.core.logger import get_logger
from app.core.auth import get_current_user
import json
import os
import time
import uuid

router = APIRouter()
logger = get_logger("MarketResearchAPI")

JOBS: dict = {}


@router.post("/research", response_model=ResearchResponse)
async def research_idea(request: ResearchRequest, current_user=Depends(get_current_user)):
    logger.info(f"[LAUNCH] Received Market Research Request: {request.idea}")
    try:
        result = await _run_research_workflow(request)
        return ResearchResponse(**result)
    except Exception as e:
        logger.error(f"[ERROR] Market Research Failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Market research failed. Please try again.")


async def _run_research_workflow(request: ResearchRequest) -> dict:
    inputs = {
        "input_idea": request.idea,
        "input_problem": request.problem,
        "input_region": request.region,
    }
    result = await market_research_app.ainvoke(inputs)
    pdf_path = result.get("pdf_path")
    json_path = result.get("json_path")
    message = result.get("market_research", "Research completed successfully.")
    research_data = {"status": "completed"}
    if json_path and os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                research_data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read JSON output: {e}")
    return {"message": message, "pdf_path": pdf_path, "json_path": json_path, "data": research_data}


async def _run_research_task(job_id: str, request: ResearchRequest, owner_id: str) -> None:
    start = time.time()
    try:
        logger.info(f"[JOB {job_id}] Market Research starting")
        result = await _run_research_workflow(request)
        duration = time.time() - start
        logger.info(f"[JOB {job_id}] Market Research completed in {duration:.2f}s")
        JOBS[job_id] = {"status": "completed", "result": result, "duration": f"{duration:.2f}s", "owner_id": owner_id}
    except Exception as e:
        logger.error(f"[JOB {job_id}] Market Research FAILED: {e}", exc_info=True)
        JOBS[job_id] = {"status": "failed", "error": "Research failed. Please try again.", "owner_id": owner_id}


@router.post("/research/start")
async def start_research(
    request: ResearchRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
):
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "running", "owner_id": current_user.id}
    background_tasks.add_task(_run_research_task, job_id, request, current_user.id)
    return {"job_id": job_id, "status": "accepted"}


@router.get("/research/status/{job_id}")
async def research_status(job_id: str, current_user=Depends(get_current_user)):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job ID not found")
    if job.get("owner_id") != current_user.id:
        raise HTTPException(status_code=404, detail="Job ID not found")
    return {k: v for k, v in job.items() if k != "owner_id"}


@router.post("/validate-idea")
async def validate_idea(request: ResearchRequest, current_user=Depends(get_current_user)):
    logger.info(f"[LAUNCH] Received Idea Validation Request: {request.idea}")
    try:
        inputs = {"idea": request.idea, "problem": request.problem, "region": request.region or "Global"}
        result = await idea_check_app.ainvoke(inputs)
        if result.get("error"):
            raise Exception(result["error"])
        return {"status": "success", "validation_data": result.get("analysis_result", {})}
    except Exception as e:
        logger.error(f"[ERROR] Idea Validation Failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Idea validation failed. Please try again.")
