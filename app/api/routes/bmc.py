import json
from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    BMCRequest,
    BMCResponse,
    BMCEnhanceRequest,
    BMCEnhanceResponse,
)
from app.core.logger import get_logger
from app.graph.BMC.workflow import bmc_app
from app.graph.BMC.node import enhance_bmc

router = APIRouter()
logger = get_logger("BMCAPI")


def _maybe_parse(payload):
    if isinstance(payload, str):
        s = payload.strip()
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            # Not JSON — keep the raw text so extract_bmc_context can use it as
            # free-text evidence instead of silently discarding it (which caused
            # the model to fabricate [Validated] claims against empty sources).
            logger.info("[BMC] Payload is free text, not JSON; passing through as raw text.")
            return s
    return payload or {}


@router.post("/generate", response_model=BMCResponse)
async def generate_bmc(request: BMCRequest):
    """Run the Business Model Canvas agent against an existing market_research payload."""
    logger.info("[LAUNCH] BMC requested for idea: %s", request.idea_name)

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


@router.post("/enhance", response_model=BMCEnhanceResponse)
async def enhance_bmc_endpoint(request: BMCEnhanceRequest):
    """Refine an existing BMC using founder-requested changes from the chat summarizer."""
    logger.info(
        "[LAUNCH] BMC enhance requested for idea: %s (%d change(s))",
        request.idea_name,
        len(request.document_changes or []),
    )

    current_bmc = _maybe_parse(request.current_bmc)
    # Unwrap {"business_model_canvas": {...}} if the caller passed the full envelope.
    if isinstance(current_bmc, dict) and "business_model_canvas" in current_bmc:
        inner = current_bmc.get("business_model_canvas")
        if isinstance(inner, dict):
            current_bmc = inner

    if not request.document_changes:
        raise HTTPException(status_code=400, detail="document_changes must be a non-empty list.")

    if not isinstance(current_bmc, dict) or not current_bmc:
        raise HTTPException(status_code=400, detail="current_bmc must be a non-empty object.")

    try:
        result = await enhance_bmc(
            idea_name=request.idea_name,
            idea_description=request.idea_description,
            region=request.region or "Global",
            current_bmc=current_bmc,
            document_changes=list(request.document_changes),
        )

        canvas = result.get("business_model_canvas")
        errors = result.get("errors") or []
        change_log = result.get("change_log") or []
        message = (
            "BMC enhanced successfully."
            if canvas and not errors
            else "BMC enhance completed with errors."
        )
        return BMCEnhanceResponse(
            message=message,
            business_model_canvas=canvas,
            change_log=change_log,
            errors=errors,
        )

    except Exception as e:
        logger.error("[BMC] Enhance failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
