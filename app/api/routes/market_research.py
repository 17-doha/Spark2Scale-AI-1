from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.graph.market_research_agent.workflow import market_research_app
from app.graph.idea_check.workflow import idea_check_app
from app.api.schemas import ResearchRequest, ResearchResponse
from app.core.logger import get_logger
import json
import os
import time
import uuid

router = APIRouter()
logger = get_logger("MarketResearchAPI")

# In-memory job store. Same pattern the Evaluation endpoint uses — sufficient
# for a single-instance Azure deployment; move to Redis if you horizontally
# scale the API.
JOBS: dict = {}

@router.post("/research", response_model=ResearchResponse)
async def research_idea(request: ResearchRequest):
    """
    Synchronous Market Research entry point — kept for direct callers (Swagger,
    backward compatibility). Times out at Azure App Service's 230s gateway
    limit for cold workflows; prefer /research/start + /research/status for
    anything user-facing.
    """
    logger.info(f"[LAUNCH] Received Market Research Request: {request.idea}")

    try:
        result = await _run_research_workflow(request)
        return ResearchResponse(**result)
    except Exception as e:
        logger.error(f"[ERROR] Market Research Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Async job pattern
# ---------------------------------------------------------------------------

async def _run_research_workflow(request: ResearchRequest) -> dict:
    """Shared workflow runner used by both the sync and background paths."""
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

    return {
        "message": message,
        "pdf_path": pdf_path,
        "json_path": json_path,
        "data": research_data,
    }


async def _run_research_task(job_id: str, request: ResearchRequest) -> None:
    """Background worker that updates the JOBS dict as work progresses."""
    start = time.time()
    try:
        logger.info(f"[JOB {job_id}] Market Research starting")
        result = await _run_research_workflow(request)
        duration = time.time() - start
        logger.info(f"[JOB {job_id}] Market Research completed in {duration:.2f}s")
        JOBS[job_id] = {
            "status": "completed",
            "result": result,
            "duration": f"{duration:.2f}s",
        }
    except Exception as e:
        logger.error(f"[JOB {job_id}] Market Research FAILED: {e}")
        JOBS[job_id] = {"status": "failed", "error": str(e)}


@router.post("/research/start")
async def start_research(request: ResearchRequest, background_tasks: BackgroundTasks):
    """
    Kick off market research in a background task and return a job id
    immediately. Caller then polls /research/status/{job_id}. Avoids Azure
    App Service's 230s front-door timeout because each HTTP call returns
    in under a second.
    """
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "running"}
    background_tasks.add_task(_run_research_task, job_id, request)
    return {"job_id": job_id, "status": "accepted"}


@router.get("/research/status/{job_id}")
async def research_status(job_id: str):
    """Polling endpoint. Mirrors /evaluate/status/{job_id}."""
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job ID not found")
    return job

@router.post("/validate-idea")
async def validate_idea(request: ResearchRequest):
    """
    Triggers the standalone Idea Check Agent to validate a problem and solution hypothesis.
    """
    logger.info(f"[LAUNCH] Received Idea Validation Request: {request.idea}")
    
    try:
        inputs = {
            "idea": request.idea,
            "problem": request.problem,
            "region": request.region or "Global"
        }
        
        result = await idea_check_app.ainvoke(inputs)
        
        if result.get("error"):
            raise Exception(result["error"])
            
        analysis = result.get("analysis_result", {})
        
        return {
            "status": "success",
            "validation_data": analysis
        }
        
    except Exception as e:
        logger.error(f"[ERROR] Idea Validation Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
