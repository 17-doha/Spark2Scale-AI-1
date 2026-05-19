import json
import os
import time
import uuid
import zipfile
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict, Any
from pydantic import BaseModel
from fastapi.responses import FileResponse
from app.utils.pdf_generator import generate_founder_report, generate_investor_report
from app.graph.evaluation_agent.helpers import normalize_input_data
from app.core.logger import get_logger
from app.graph.evaluation_agent import evaluation_graph
# from app.core.metrics import evaluation_requests, langgraph_duration
import time

router = APIRouter()
logger = get_logger(__name__)

# --- In-Memory Job Store ---
# Note: In production, consider using Redis if you scale to multiple server instances.
JOBS = {}

class RawInput(BaseModel):
    data: Any

# =========================================================
# 1. BACKGROUND WORKER LOGIC
# =========================================================

async def run_evaluation_task(job_id: str, normalized_data: dict):
    start_time = time.time()
    try:
        state = await evaluation_graph.ainvoke({"user_data": normalized_data})
        evaluation_requests.labels(status="success").inc()
        # ... existing code
    except Exception as e:
        evaluation_requests.labels(status="error").inc()
        raise
    finally:
        langgraph_duration.labels(workflow="evaluation").observe(
            time.time() - start_time
        )
        
async def run_evaluation_task(job_id: str, normalized_data: dict):
    """
    Handles the heavy lifting in the background.
    """
    start_time = time.time()
    try:
        logger.info(f"[JOB {job_id}] Starting LangGraph execution...")
        
        # Execute the AI Graph
        state = await evaluation_graph.ainvoke({"user_data": normalized_data})
        
        # Extract the reports from the final state
        full_report = {
            "team_report": state.get("team_report"),
            "problem_report": state.get("problem_report"),
            "product_report": state.get("product_report"),
            "market_report": state.get("market_report"),
            "traction_report": state.get("traction_report"),
            "gtm_report": state.get("gtm_report"),
            "business_report": state.get("business_report"),
            "vision_report": state.get("vision_report"),
            "operations_report": state.get("operations_report"),
            "final_report": state.get("final_report")
        }
        
        duration = time.time() - start_time
        logger.info(f"[JOB {job_id}] COMPLETED in {duration:.2f}s")

        JOBS[job_id] = {
            "status": "completed",
            "result": full_report,
            "duration": f"{duration:.2f}s"
        }

    except Exception as e:
        logger.error(f"[JOB {job_id}] FAILED: {str(e)}")
        JOBS[job_id] = {
            "status": "failed",
            "error": str(e)
        }

# =========================================================
# 2. ENDPOINTS
# =========================================================

@router.post("/evaluate/all")
async def evaluate_all(raw_payload: RawInput, background_tasks: BackgroundTasks):
    """
    Starts evaluation and returns a Job ID immediately.
    """
    # 1. Normalize (keep this fast)
    raw_str = json.dumps(raw_payload.data) if isinstance(raw_payload.data, dict) else str(raw_payload.data)
    
    try:
        # We normalize here to catch immediate schema errors before backgrounding
        normalized_data = await normalize_input_data(raw_str)
        
        job_id = str(uuid.uuid4())
        JOBS[job_id] = {"status": "running"}
        
        # 2. Offload to background
        background_tasks.add_task(run_evaluation_task, job_id, normalized_data)
        
        return {
            "job_id": job_id,
            "status": "accepted",
            "message": "Evaluation started in background"
        }

    except Exception as e:
        logger.error(f"[ERROR] Launch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/evaluate/status/{job_id}")
async def get_status(job_id: str):
    """
    Polling endpoint for the frontend.
    """
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job ID not found")
    
    return job

@router.post("/generate-report")
async def generate_reports_endpoint(report_data: Dict[str, Any]):
    # (Same as your previous PDF logic)
    try:
        os.makedirs("outputs", exist_ok=True)
        base_id = uuid.uuid4().hex[:6]
        f_path, i_path = f"outputs/F_{base_id}.pdf", f"outputs/I_{base_id}.pdf"
        
        generate_founder_report(report_data, f_path)
        generate_investor_report(report_data, i_path)
        
        zip_filename = f"outputs/Eval_{base_id}.zip"
        with zipfile.ZipFile(zip_filename, 'w') as zipf:
            zipf.write(f_path, os.path.basename(f_path))
            zipf.write(i_path, os.path.basename(i_path))
            
        return FileResponse(path=zip_filename, filename="Spark2Scale_Package.zip")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))