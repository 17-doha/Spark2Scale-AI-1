from fastapi import APIRouter, HTTPException
from app.graph.document_generator.workflow import document_generator_app
from app.api.schemas import SWOTRequest, SWOTResponse
from app.core.logger import get_logger

router = APIRouter()
logger = get_logger("SWOTAPI")

@router.post("/generate", response_model=SWOTResponse)
async def generate_swot(request: SWOTRequest):
    """
    Triggers the Document Generator Agent to generate a SWOT analysis.
    """
    logger.info(f"[LAUNCH] Received SWOT Generation Request: {request.idea_name}")
    
    try:
        # Invoke the LangGraph workflow
        initial_state = {
            "idea_name": request.idea_name,
            "idea_description": request.idea_description,
            "region": request.region or "Global",
            "market_research": request.market_research
        }
        
        # We use ainvoke for asynchronous execution of the graph
        result = await document_generator_app.ainvoke(initial_state)
        
        swot_doc = result.get("swot_document")
        errors = result.get("errors", [])
        
        message = "SWOT generation completed successfully." if not errors else "SWOT generation completed with errors."
        
        return SWOTResponse(
            message=message,
            swot_document=swot_doc,
            errors=errors
        )
        
    except Exception as e:
        logger.error(f"[ERROR] SWOT Generation Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
