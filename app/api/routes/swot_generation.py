import json
import os
from fastapi import APIRouter, HTTPException
from app.graph.document_generator.workflow import document_generator_app
from app.api.schemas import SWOTRequest, SWOTResponse
from app.core.logger import get_logger

router = APIRouter()
logger = get_logger("SWOTAPI")

DEBUG_DUMP_PATH = "data_output/debug_swot_input.json"

def _dump_debug(payload: dict):
    """Saves the full incoming request payload to a JSON file for inspection."""
    try:
        os.makedirs("data_output", exist_ok=True)
        with open(DEBUG_DUMP_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        logger.info(f"[DEBUG] Full input payload saved to: {DEBUG_DUMP_PATH}")
    except Exception as e:
        logger.warning(f"[DEBUG] Could not save debug dump: {e}")


@router.post("/generate", response_model=SWOTResponse)
async def generate_swot(request: SWOTRequest):
    """
    Triggers the Document Generator Agent to generate a SWOT analysis.
    """
    logger.info(f"[LAUNCH] Received SWOT Generation Request: {request.idea_name}")

    try:
        # ── STEP 1: Raw receipt ───────────────────────────────────────────────
        mr_raw = request.market_research
        logger.info(f"[DEBUG] market_research type on arrival: {type(mr_raw).__name__}")

        # ── STEP 2: If it's a string, try to parse it ─────────────────────────
        mr_data = mr_raw
        if isinstance(mr_data, str):
            logger.info(f"[DEBUG] market_research is a STRING. First 300 chars: {mr_data[:300]}")
            try:
                mr_data = json.loads(mr_data)
                logger.info(f"[DEBUG] Parsed string → type is now: {type(mr_data).__name__}")
            except json.JSONDecodeError as e:
                logger.error(f"[ERROR] Failed to parse market_research string into JSON: {e}")
                mr_data = {}

        # ── STEP 3: Unwrap list ───────────────────────────────────────────────
        if isinstance(mr_data, list):
            logger.info(f"[DEBUG] market_research is a LIST of length {len(mr_data)}. Unwrapping index 0.")
            mr_data = mr_data[0] if len(mr_data) > 0 else {}

        # ── STEP 4: C# wraps arrays under "items" — unwrap that too ──────────
        if isinstance(mr_data, dict) and "items" in mr_data and isinstance(mr_data.get("items"), list):
            logger.info(f"[DEBUG] Found C# 'items' wrapper. Unwrapping.")
            items = mr_data["items"]
            mr_data = items[0] if len(items) > 0 else {}

        # ── STEP 5: Log the top-level keys so we can see the structure ────────
        if isinstance(mr_data, dict):
            top_keys = list(mr_data.keys())
            logger.info(f"[DEBUG] market_research top-level keys: {top_keys}")

            # Check one level deeper for the "data" key
            inner = mr_data.get("data")
            if inner is not None:
                logger.info(f"[DEBUG] 'data' key exists. Type: {type(inner).__name__}")
                if isinstance(inner, dict):
                    logger.info(f"[DEBUG] 'data' sub-keys: {list(inner.keys())}")
                elif isinstance(inner, list):
                    logger.info(f"[DEBUG] 'data' is a LIST of length {len(inner)}")
                    if len(inner) > 0:
                        logger.info(f"[DEBUG] First element type: {type(inner[0]).__name__}")
                        if isinstance(inner[0], dict):
                            logger.info(f"[DEBUG] First element keys: {list(inner[0].keys())}")
            else:
                logger.warning(f"[DEBUG] No 'data' key found inside market_research. This is the bug.")
        else:
            logger.warning(f"[DEBUG] After all unwrapping, market_research is STILL not a dict. Type: {type(mr_data).__name__}")

        # ── STEP 6: Save full dump to disk ────────────────────────────────────
        _dump_debug({
            "idea_name": request.idea_name,
            "idea_description": request.idea_description,
            "region": request.region,
            "market_research_type": type(mr_data).__name__,
            "market_research": mr_data,
            "comment": request.comment
        })

        # ── STEP 7: Build state and run graph ─────────────────────────────────
        initial_state = {
            "document_type": "swot",
            "idea_name": request.idea_name,
            "idea_description": request.idea_description,
            "region": request.region or "Global",
            "market_research": mr_data,
            "comment": request.comment
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