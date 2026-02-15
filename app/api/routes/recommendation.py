import time
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional

# --- Import Logger ---
from app.utils.logger import logger

# --- Import Recommendation Logic ---
from app.graph.recommendation_agent.workflow import run_recommendation_agent
from app.core.config import Config

router = APIRouter()

class RecommendationInput(BaseModel):
    raw_input: Dict[str, Any]  # The original startup data
    evaluation_output: Dict[str, Any]  # The output from the evaluation agent
    request_id: Optional[str] = None

@router.post("/recommend")
async def get_recommendations(input_data: RecommendationInput):
    """
    Endpoint to trigger the Strategic Recommendation Agent.
    It processes evaluation scores and generates experiment-led advice.
    """
    start_time = time.time()
    logger.info(f"🚀 Recommendation Agent triggered for Request ID: {input_data.request_id}")

    # Ensure API Key is present
    api_key = Config.GEMINI_API_KEY
    if not api_key:
        logger.error("❌ GEMINI_API_KEY is missing in configuration.")
        raise HTTPException(status_code=500, detail="Gemini API Key not configured.")

    try:
        # Execute the workflow
        # Note: run_recommendation_agent handles pattern detection and AI synthesis
        result = run_recommendation_agent(
            raw_input=input_data.raw_input,
            eval_output=input_data.evaluation_output,
            api_key=api_key,
            save_output=True,
            request_id=input_data.request_id
        )

        duration = time.time() - start_time
        logger.info(f"✅ Recommendation workflow finished in {duration:.2f}s")
        
        return result

    except Exception as e:
        logger.error(f"❌ Recommendation Agent Failed: {str(e)}")
        # Provide more context if it's a validation error
        if "validation error" in str(e).lower():
            raise HTTPException(status_code=422, detail=f"Data Schema Mismatch: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))