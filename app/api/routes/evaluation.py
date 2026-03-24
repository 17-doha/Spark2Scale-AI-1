import json
import os
import time
import uuid
import zipfile
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from pydantic import BaseModel
from fastapi.responses import FileResponse

# --- Imports ---
from app.utils.pdf_generator import generate_founder_report, generate_investor_report
from app.graph.evaluation_agent.helpers import normalize_input_data
from app.core.logger import get_logger
from app.graph.evaluation_agent import evaluation_graph

router = APIRouter()
logger = get_logger(__name__)

class RawInput(BaseModel):
    data: Any

# --- Helper to Save JSON (Optional Debugging) ---
def save_agent_output(agent_id: str, data: dict):
    directory = "outputs"
    os.makedirs(directory, exist_ok=True)
    filepath = os.path.join(directory, f"report_{agent_id}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# =========================================================
# 1. EVALUATE ALL (Blocking Version)
# =========================================================

@router.post("/evaluate/all")
async def evaluate_all(raw_payload: RawInput):
    """
    Performs the full AI evaluation synchronously.
    The response is only sent once the AI work is finished.
    """
    start_time = time.time()
    
    # 1. Normalize Data
    raw_str = json.dumps(raw_payload.data) if isinstance(raw_payload.data, dict) else str(raw_payload.data)
    
    try:
        normalized_data = await normalize_input_data(raw_str)
        
        logger.info("[START] Starting Synchronous Evaluation...")
        
        # 2. Run the LangGraph (Awaited directly)
        state = await evaluation_graph.ainvoke({"user_data": normalized_data})
        
        # 3. Format the result
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
        logger.info(f"[SUCCESS] Evaluation COMPLETED in {duration:.2f}s")

        return {
            "status": "completed",
            "duration": f"{duration:.2f}s",
            "result": full_report
        }

    except Exception as e:
        logger.error(f"[ERROR] Evaluation Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# 2. GENERATE REPORT (Unchanged)
# =========================================================

@router.post("/generate-report")
async def generate_reports_endpoint(report_data: Dict[str, Any]):
    try:
        os.makedirs("outputs", exist_ok=True)
        base_id = uuid.uuid4().hex[:6]
        
        f_path = f"outputs/Founder_Report_{base_id}.pdf"
        generate_founder_report(report_data, f_path)
        
        i_path = f"outputs/Investor_Memo_{base_id}.pdf"
        generate_investor_report(report_data, i_path)
        
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