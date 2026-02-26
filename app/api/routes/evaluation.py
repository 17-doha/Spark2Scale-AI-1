import json
import os
import time
import asyncio
import uuid
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict, Any
from pydantic import BaseModel
from fastapi.responses import FileResponse, JSONResponse
from app.utils.pdf_generator import generate_founder_report, generate_investor_report
import zipfile
from app.graph.evaluation_agent.helpers import normalize_input_data

# --- Import Logger ---
from app.core.logger import get_logger

# --- Import the Main Graph ---
from app.graph.evaluation_agent import evaluation_graph

router = APIRouter()
logger = get_logger(__name__)

# --- In-Memory Job Store ---
# Stores the status and results of background tasks
JOBS = {}

class RawInput(BaseModel):
    data: Any

class EvalInput(BaseModel):
    startup_evaluation: Dict[str, Any]

# --- Helper to Save JSON ---
def save_agent_output(agent_name: str, data: dict):
    directory = "outputs"
    if not os.path.exists(directory):
        os.makedirs(directory)
    
    filepath = os.path.join(directory, f"{agent_name}_output.json")
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    
    logger.info(f"[SAVE] Saved {agent_name} output to {filepath}")


# =========================================================
# 1. BACKGROUND TASK LOGIC
# =========================================================

async def run_evaluation_background(job_id: str, normalized_data: dict):
    """
    This function runs in the background. It performs the heavy
    AI work and updates the JOBS dictionary when finished.
    """
    start_time = time.time()
    logger.info(f"[LAUNCH] Job {job_id}: Starting Background Evaluation...")

    try:
        # Run the full LangGraph
        state = await evaluation_graph.ainvoke({"user_data": normalized_data})
        
        # Filter output
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
        
        # Save output to disk (optional debugging)
        save_agent_output(f"JOB_{job_id}", full_report)
        
        duration = time.time() - start_time
        logger.info(f"\n{'='*60}")
        logger.info(f"[SUCCESS] Job {job_id}: Evaluation COMPLETED in {duration:.2f}s")
        logger.info(f"{'='*60}")
        
        # Update Job Status to Completed
        JOBS[job_id] = {
            "status": "completed",
            "result": full_report
        }

    except Exception as e:
        logger.error(f"[ERROR] Job {job_id} Failed: {e}")
        JOBS[job_id] = {
            "status": "failed",
            "error": str(e)
        }


# =========================================================
# 2. START EVALUATION ENDPOINT
# =========================================================

@router.post("/evaluate/all")
async def evaluate_all(raw_payload: RawInput, background_tasks: BackgroundTasks):
    """
    Starts the evaluation in the background.
    Returns a 'job_id' immediately so the connection doesn't timeout.
    """
    # 1. Normalize Data (Fast)
    # Convert input to string if it's a dict
    raw_str = json.dumps(raw_payload.data) if isinstance(raw_payload.data, dict) else str(raw_payload.data)
    
    try:
        normalized_data = await normalize_input_data(raw_str)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Normalization failed: {str(e)}")
    
    # 2. Generate Job ID
    job_id = str(uuid.uuid4())
    
    # 3. Set Initial Status
    JOBS[job_id] = {"status": "running"}
    
    # 4. Add to Background Tasks (This prevents blocking/timeout)
    background_tasks.add_task(run_evaluation_background, job_id, normalized_data)
    

    
    return {
        "message": "Evaluation started", 
        "job_id": job_id,
        "status_url": f"/api/evaluate/status/{job_id}" 
    }


# =========================================================
# 3. CHECK STATUS ENDPOINT (New!)
# =========================================================

@router.get("/evaluate/status/{job_id}")
async def get_job_status(job_id: str):
    """
    Call this repeatedly (poll) to check if the job is done.
    """
    job = JOBS.get(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job ID not found")
        
    if job["status"] == "running":
        return {"status": "running", "message": "AI is working..."}
    
    if job["status"] == "failed":
        return {"status": "failed", "error": job.get("error")}
        
    # If completed, return the result
    return {
        "status": "completed", 
        "result": job["result"]
    }


# =========================================================
# 4. GENERATE REPORT (Unchanged)
# =========================================================

@router.post("/generate-report")
async def generate_reports_endpoint(report_data: Dict[str, Any]):
    """
    Generates both Founder and Investor reports and returns them as a ZIP.
    """
    try:
        # Create output dir
        os.makedirs("outputs", exist_ok=True)
        base_id = uuid.uuid4().hex[:6]
        
        # 1. Generate Founder PDF
        f_path = f"outputs/Founder_Report_{base_id}.pdf"
        generate_founder_report(report_data, f_path)
        
        # 2. Generate Investor PDF
        i_path = f"outputs/Investor_Memo_{base_id}.pdf"
        generate_investor_report(report_data, i_path)
        
        # 3. Zip them together
        zip_filename = f"outputs/Evaluation_Package_{base_id}.zip"
        with zipfile.ZipFile(zip_filename, 'w') as zipf:
            zipf.write(f_path, os.path.basename(f_path))
            zipf.write(i_path, os.path.basename(i_path))
            
        return FileResponse(
            path=zip_filename, 
            filename="Spark2Scale_Evaluation_Package.zip", 
            media_type='application/zip'
        )
        
    except Exception as e:
        logger.error(f"[ERROR] PDF Generation Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))