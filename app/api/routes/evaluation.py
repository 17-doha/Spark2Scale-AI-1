import json
import os
import time
import uuid
import zipfile
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import Dict, Any
from pydantic import BaseModel
from fastapi.responses import FileResponse
from app.utils.pdf_generator import generate_founder_report, generate_investor_report
from app.graph.evaluation_agent.helpers import normalize_input_data
from app.core.logger import get_logger
from app.core.auth import get_current_user
from app.graph.evaluation_agent import evaluation_graph
import time

router = APIRouter()
logger = get_logger(__name__)

JOBS = {}

class RawInput(BaseModel):
    data: Any


async def run_evaluation_task(job_id: str, normalized_data: dict, owner_id: str):
    start_time = time.time()
    try:
        logger.info(f"[JOB {job_id}] Starting LangGraph execution...")
        state = await evaluation_graph.ainvoke({"user_data": normalized_data})
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
            "final_report": state.get("final_report"),
        }
        duration = time.time() - start_time
        logger.info(f"[JOB {job_id}] COMPLETED in {duration:.2f}s")
        JOBS[job_id] = {"status": "completed", "result": full_report, "duration": f"{duration:.2f}s", "owner_id": owner_id}
    except Exception as e:
        logger.error(f"[JOB {job_id}] FAILED: {str(e)}", exc_info=True)
        JOBS[job_id] = {"status": "failed", "error": "Evaluation failed. Please try again.", "owner_id": owner_id}


@router.post("/evaluate/all")
async def evaluate_all(
    raw_payload: RawInput,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
):
    raw_str = json.dumps(raw_payload.data) if isinstance(raw_payload.data, dict) else str(raw_payload.data)
    try:
        normalized_data = await normalize_input_data(raw_str)
        job_id = str(uuid.uuid4())
        JOBS[job_id] = {"status": "running", "owner_id": current_user.id}
        background_tasks.add_task(run_evaluation_task, job_id, normalized_data, current_user.id)
        return {"job_id": job_id, "status": "accepted", "message": "Evaluation started in background"}
    except Exception as e:
        logger.error(f"[ERROR] Launch failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to start evaluation. Please try again.")


@router.get("/evaluate/status/{job_id}")
async def get_status(job_id: str, current_user=Depends(get_current_user)):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job ID not found")
    if job.get("owner_id") != current_user.id:
        raise HTTPException(status_code=404, detail="Job ID not found")
    return {k: v for k, v in job.items() if k != "owner_id"}


@router.post("/generate-report")
async def generate_reports_endpoint(
    report_data: Dict[str, Any],
    current_user=Depends(get_current_user),
):
    try:
        os.makedirs("outputs", exist_ok=True)
        base_id = uuid.uuid4().hex[:6]
        f_path, i_path = f"outputs/F_{base_id}.pdf", f"outputs/I_{base_id}.pdf"
        generate_founder_report(report_data, f_path)
        generate_investor_report(report_data, i_path)
        zip_filename = f"outputs/Eval_{base_id}.zip"
        with zipfile.ZipFile(zip_filename, "w") as zipf:
            zipf.write(f_path, os.path.basename(f_path))
            zipf.write(i_path, os.path.basename(i_path))
        return FileResponse(path=zip_filename, filename="Spark2Scale_Package.zip")
    except Exception as e:
        logger.error(f"[ERROR] Report generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Report generation failed. Please try again.")
