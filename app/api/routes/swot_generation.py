import json
from fastapi import APIRouter, HTTPException
from app.graph.document_generator.workflow import document_generator_app
from app.api.schemas import SWOTRequest, SWOTResponse
from app.core.logger import get_logger

router = APIRouter()
logger = get_logger("SWOTAPI")

def _sanitize_market_research(mr_data):
    """
    Recursively ensures the incoming market research is perfectly formatted.
    Parses Stringified JSON from the C# Backend into a Python Dictionary.
    """
    if not mr_data:
        return {}
        
    # 1. If C# sent it as a Stringified JSON, parse it back to an object
    if isinstance(mr_data, str):
        try:
            mr_data = json.loads(mr_data)
        except json.JSONDecodeError:
            return {}

    # 2. If the root is a list, take the first item
    if isinstance(mr_data, list):
        mr_data = mr_data[0] if len(mr_data) > 0 else {}

    # 3. Ensure 'data' is a dict
    if isinstance(mr_data, dict) and "data" in mr_data:
        data_block = mr_data["data"]
        
        if isinstance(data_block, str):
            try:
                data_block = json.loads(data_block)
            except:
                data_block = {}
                
        if isinstance(data_block, list):
            data_block = data_block[0] if len(data_block) > 0 else {}
            
        mr_data["data"] = data_block
            
        # 4. Ensure competitors are valid objects
        if isinstance(data_block, dict) and "competitors" in data_block:
            competitors = data_block["competitors"]
            if isinstance(competitors, list):
                clean_competitors = [c for c in competitors if isinstance(c, dict)]
                mr_data["data"]["competitors"] = clean_competitors

    return mr_data if isinstance(mr_data, dict) else {}


@router.post("/generate", response_model=SWOTResponse)
async def generate_swot(request: SWOTRequest):
    logger.info(f"[LAUNCH] Received SWOT Generation Request: {request.idea_name}")
    try:
        # CLEAN THE DATA (Parses C# Strings to Python Dicts)
        safe_market_research = _sanitize_market_research(request.market_research)

        initial_state = {
            "idea_name": request.idea_name,
            "idea_description": request.idea_description,
            "region": request.region or "Global",
            "market_research": safe_market_research
        }
        
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