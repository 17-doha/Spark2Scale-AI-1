import json
import os
import re
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

# BMC generation + enhancement run on Gemini by default. Env-overridable:
# set BMC_LLM_PROVIDER=groq|ollama (and optionally BMC_LLM_MODEL) to switch.
BMC_LLM_PROVIDER = os.environ.get("BMC_LLM_PROVIDER", "gemini")
BMC_LLM_MODEL = os.environ.get("BMC_LLM_MODEL") or None

# --- Citation-integrity guard --------------------------------------------------
# The prompt asks the model to only cite real, available sources and to tag
# inferred claims [Hypothesis] — but LLMs don't reliably comply. This guard
# enforces it deterministically after generation.
_SOURCE_TAG_RE = re.compile(r"\s*\[Source:\s*([^\]]*)\]\s*$", re.IGNORECASE)
_VALIDATED_PREFIX_RE = re.compile(r"^\s*\[\s*validated\s*\]", re.IGNORECASE)

# Granular source labels that must NOT be cited unless that data is actually present.
_GRANULAR_SOURCES = (
    "competitors", "market sizing", "opportunity analysis", "validation",
    "trends", "finance", "pricing", "startup costs", "monthly fixed costs",
    "customer quotes",
)


def _source_allowed(src: str, available_lower: set) -> bool:
    """True if a citation only references sources that genuinely exist."""
    s = (src or "").strip().lower()
    if not s or s in ("none", "n/a", "na"):
        return False
    # Deny if it names a granular source that isn't available (e.g. "Finance" when
    # no finance data was provided) — even if a broader family token also matches.
    for g in _GRANULAR_SOURCES:
        if g in s and g not in available_lower:
            return False
    # Otherwise require at least one available source token to appear.
    return any(tok in s for tok in available_lower)


def _enforce_integrity(canvas: Dict[str, Any], available: List[str]) -> Dict[str, Any]:
    """Downgrade `[Validated]` bullets that cite unavailable/empty sources to
    `[Hypothesis]` (stripping the bogus citation), and remove stray source tags
    (e.g. `[Source: None]`) from `[Hypothesis]` bullets."""
    available_lower = {a.lower() for a in (available or [])}
    cleaned: Dict[str, Any] = {}
    for block, bullets in (canvas or {}).items():
        out: List[str] = []
        for bullet in (bullets or []):
            text = str(bullet).strip()
            m = _SOURCE_TAG_RE.search(text)
            src = m.group(1).strip() if m else ""
            body = _SOURCE_TAG_RE.sub("", text).rstrip()
            is_validated = bool(_VALIDATED_PREFIX_RE.match(body))
            if is_validated and _source_allowed(src, available_lower):
                out.append(f"{body} [Source: {src}]")
            else:
                if is_validated:  # cited a missing/empty source → downgrade
                    body = _VALIDATED_PREFIX_RE.sub("[Hypothesis]", body, count=1)
                out.append(body.strip())  # hypotheses never keep a source tag
        cleaned[block] = out
    return cleaned


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

    available = context.get("available_evidence") or []
    prompt_user = USER_TEMPLATE.format(
        idea_name=context.get("idea_name", ""),
        idea_description=context.get("idea_description", ""),
        region=context.get("region", "Global"),
        available_evidence=", ".join(available) if available else "NONE — treat every bullet as [Hypothesis].",
        context_json=json.dumps(context, indent=2, default=str),
    )

    try:
        llm = get_llm(provider=BMC_LLM_PROVIDER, model_name=BMC_LLM_MODEL, temperature=0.2)
        response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt_user),
        ])
        raw = response.content if hasattr(response, "content") else str(response)
        logger.info("[BMC] Gemini returned %d chars.", len(raw or ""))

        parsed = _parse_llm_json(raw)
        envelope = BMCEnvelope(**parsed)
        canvas = envelope.business_model_canvas.model_dump()
        # Deterministic citation-integrity pass — strips fabricated citations the
        # LLM produced despite the prompt rules.
        canvas = _enforce_integrity(canvas, context.get("available_evidence") or [])
        return {"business_model_canvas": canvas}

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
        llm = get_llm(provider=BMC_LLM_PROVIDER, model_name=BMC_LLM_MODEL, temperature=0.2)
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
