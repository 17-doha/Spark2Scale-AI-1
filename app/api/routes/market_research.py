from fastapi import APIRouter, HTTPException
from app.graph.market_research_agent.workflow import market_research_app
from app.api.schemas import ResearchRequest, ResearchResponse
from app.core.logger import get_logger
import json
import os

router = APIRouter()
logger = get_logger("MarketResearchAPI")

@router.post("/research", response_model=ResearchResponse)
async def research_idea(request: ResearchRequest):
    """
    Triggers the Market Research Agent for a given idea and problem statement.
    """
    logger.info(f"🚀 Received Market Research Request: {request.idea}")
    
    try:
        # Invoke the LangGraph workflow
        # The state expects "input_idea" and "input_problem"
        inputs = {
            "input_idea": request.idea,
            "input_problem": request.problem
        }
        
        result = await market_research_app.ainvoke(inputs)
        
        # Extract results from the final state
        pdf_path = result.get("pdf_path")
        json_path = result.get("json_path")
        message = result.get("market_research", "Research completed successfully.")
        
        # Read the JSON data from the file if it exists
        research_data = {"status": "completed"}
        if json_path and os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    research_data = json.load(f)
            except Exception as e:
                logger.error(f"Failed to read JSON output: {e}")
        
        return ResearchResponse(
            message=message,
            pdf_path=pdf_path,
            json_path=json_path,
            data=research_data
        )
        
    except Exception as e:
        logger.error(f"❌ Market Research Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
