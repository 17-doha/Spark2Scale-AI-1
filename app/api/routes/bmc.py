import json
from fastapi import APIRouter, HTTPException

from app.api.schemas import BMCRequest, BMCResponse
from app.core.logger import get_logger
from app.graph.BMC.workflow import bmc_app

router = APIRouter()
logger = get_logger("BMCAPI")


@router.post("/generate", response_model=BMCResponse)
async def generate_bmc(request: BMCRequest):
    """Run the Business Model Canvas agent against an existing market_research payload."""
    logger.info("[LAUNCH] BMC requested for idea: %s", request.idea_name)

    def _maybe_parse(payload):
        if isinstance(payload, str):
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                logger.warning("[BMC] Could not parse string payload as JSON; using {}.")
                return {}
        return payload or {}

    mr = _maybe_parse(request.market_research)
    ev = _maybe_parse(request.evaluation)
    rec = _maybe_parse(request.recommendation)

    try:
        initial_state = {
            "idea_name": request.idea_name,
            "idea_description": request.idea_description,
            "region": request.region or "Global",
            "market_research": mr,
            "evaluation": ev,
            "recommendation": rec,
        }
        result = await bmc_app.ainvoke(initial_state)

        canvas = result.get("business_model_canvas")
        errors = result.get("errors") or []
        message = (
            "BMC generated successfully."
            if canvas and not errors
            else "BMC generation completed with errors."
        )
        return BMCResponse(message=message, business_model_canvas=canvas, errors=errors)

    except Exception as e:
        logger.error("[BMC] Generation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
