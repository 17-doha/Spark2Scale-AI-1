import json
import os
import time
import asyncio
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from pydantic import BaseModel
from fastapi.responses import FileResponse
from app.utils.pdf_generator import generate_founder_report, generate_investor_report
import zipfile
import uuid
from app.graph.evaluation_agent.helpers import normalize_input_data

# --- Import Logger ---
from app.core.logger import get_logger


# --- Import the Main Graph ---
from app.graph.evaluation_agent import evaluation_graph

router = APIRouter()
logger = get_logger(__name__)

class EvalInput(BaseModel):
    startup_evaluation: Dict[str, Any]


class RawInput(BaseModel):
    data: Any

# --- Helper to Save JSON ---
def save_agent_output(agent_name: str, data: dict):
    directory = "outputs"
    if not os.path.exists(directory):
        os.makedirs(directory)
    
    filepath = os.path.join(directory, f"{agent_name}_output.json")
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    
    logger.info(f"💾 Saved {agent_name} output to {filepath}")



# =========================================================
# 2. MAIN "RUN ALL" ENDPOINT
# =========================================================

@router.post("/evaluate/all")
async def evaluate_all(raw_payload: RawInput):
    start_time = time.time()
    
    # 1. NORMALIZE (The new first step)
    # Convert input to string if it's a dict to pass to LLM prompt
    raw_str = json.dumps(raw_payload.data) if isinstance(raw_payload.data, dict) else str(raw_payload.data)
    
    normalized_data = await normalize_input_data(raw_str)
    
    # 2. RUN PIPELINE (Pass normalized data)
    logger.info("🚀 Starting FULL Evaluation Pipeline with Normalized Data...")
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
        
        save_agent_output("FULL_REPORT", full_report)
        
        duration = time.time() - start_time
        logger.info(f"✅ FULL Evaluation finished in {duration:.2f}s")
        return full_report
        
    except Exception as e:
        logger.error(f"❌ Full Evaluation Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
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
        logger.error(f"❌ PDF Generation Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))