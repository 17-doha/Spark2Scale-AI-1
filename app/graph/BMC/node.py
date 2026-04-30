import json
from typing import Any, Dict, List

from langchain_core.messages import SystemMessage, HumanMessage
from json_repair import repair_json
from pydantic import ValidationError

from app.core.llm import get_llm
from app.core.logger import get_logger
from .helpers import extract_bmc_context
from .prompts import (
    SYSTEM_PROMPT,
    USER_TEMPLATE,
    ENHANCE_SYSTEM_PROMPT,
    ENHANCE_USER_TEMPLATE,
)
from .schema import BMCEnvelope
from .state import BMCState

logger = get_logger("BMCNode")


def extract_context_node(state: BMCState) -> Dict[str, Any]:
    """Reduce the raw inputs to only the slices the prompt needs."""
    context = extract_bmc_context(
        idea_name=state.get("idea_name", ""),
        idea_description=state.get("idea_description", ""),
        region=state.get("region", "Global"),
        market_research=state.get("market_research", {}),
        evaluation=state.get("evaluation", {}),
        recommendation=state.get("recommendation", {}),
    )
    logger.info(
        "[BMC] Context built. has_finance=%s, has_startup_costs=%s, competitors=%d, has_evaluation=%s, has_recommendation=%s",
        bool(context.get("finance")),
        bool(context.get("startup_costs")),
        len(context.get("competitors") or []),
        bool(context.get("evaluation")),
        bool(context.get("recommendation")),
    )
    return {"extracted_context": context}


def _parse_llm_json(raw: str) -> Dict[str, Any]:
    """Parse LLM output as JSON, falling back to json_repair for stray markdown."""
    text = raw.strip()
    if text.startswith("```"):
        # strip ```json ... ``` fences
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("[BMC] Strict JSON parse failed; attempting json_repair.")
        repaired = repair_json(text)
        return json.loads(repaired)


def generate_bmc_node(state: BMCState) -> Dict[str, Any]:
    """Single Gemini call that produces the BMC JSON."""
    errors = list(state.get("errors") or [])
    context = state.get("extracted_context") or {}

    prompt_user = USER_TEMPLATE.format(
        idea_name=context.get("idea_name", ""),
        idea_description=context.get("idea_description", ""),
        region=context.get("region", "Global"),
        context_json=json.dumps(context, indent=2, default=str),
    )

    try:
        llm = get_llm(provider="gemini", temperature=0.2)
        response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt_user),
        ])
        raw = response.content if hasattr(response, "content") else str(response)
        logger.info("[BMC] Gemini returned %d chars.", len(raw or ""))

        parsed = _parse_llm_json(raw)
        envelope = BMCEnvelope(**parsed)
        return {"business_model_canvas": envelope.business_model_canvas.model_dump()}

    except ValidationError as ve:
        msg = f"BMC schema validation failed: {ve}"
        logger.error("[BMC] %s", msg)
        errors.append(msg)
        return {"business_model_canvas": None, "errors": errors}
    except Exception as e:
        msg = f"BMC generation failed: {e}"
        logger.error("[BMC] %s", msg)
        errors.append(msg)
        return {"business_model_canvas": None, "errors": errors}


async def enhance_bmc(
    idea_name: str,
    idea_description: str,
    region: str,
    current_bmc: Dict[str, Any],
    document_changes: List[str],
) -> Dict[str, Any]:
    """Single Gemini call that refines an existing BMC using founder-requested changes.

    Returns a dict of the form:
        {
            "business_model_canvas": {...} | None,
            "change_log": [...],
            "errors": [...]
        }
    """
    errors: List[str] = []

    prompt_user = ENHANCE_USER_TEMPLATE.format(
        idea_name=idea_name or "",
        idea_description=idea_description or "",
        region=region or "Global",
        current_bmc_json=json.dumps(current_bmc or {}, indent=2, default=str),
        document_changes_json=json.dumps(document_changes or [], indent=2, ensure_ascii=False),
    )

    try:
        llm = get_llm(provider="gemini", temperature=0.2)
        response = await llm.ainvoke([
            SystemMessage(content=ENHANCE_SYSTEM_PROMPT),
            HumanMessage(content=prompt_user),
        ])
        raw = response.content if hasattr(response, "content") else str(response)
        logger.info("[BMC] Enhance returned %d chars.", len(raw or ""))

        parsed = _parse_llm_json(raw)

        # Validate only the canvas block — change_log is free-form.
        envelope = BMCEnvelope(business_model_canvas=parsed.get("business_model_canvas", {}))
        change_log = parsed.get("change_log") or []
        if not isinstance(change_log, list):
            change_log = [str(change_log)]

        return {
            "business_model_canvas": envelope.business_model_canvas.model_dump(),
            "change_log": [str(x) for x in change_log],
            "errors": errors,
        }

    except ValidationError as ve:
        msg = f"BMC enhance schema validation failed: {ve}"
        logger.error("[BMC] %s", msg)
        errors.append(msg)
        return {"business_model_canvas": None, "change_log": [], "errors": errors}
    except Exception as e:
        msg = f"BMC enhance failed: {e}"
        logger.error("[BMC] %s", msg)
        errors.append(msg)
        return {"business_model_canvas": None, "change_log": [], "errors": errors}
