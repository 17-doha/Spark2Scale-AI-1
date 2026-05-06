import json
import re
import copy

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.core.llm import get_llm
from app.core.logger import get_logger
from app.graph.pdf_extractor.state import PDFExtractorState
from app.graph.pdf_extractor.tools import extract_text_from_pdf, force_numeric_types
from app.graph.pdf_extractor.prompts import PDF_EXTRACTION_PROMPT
from app.graph.pdf_extractor.schema import TARGET_SCHEMA

logger = get_logger(__name__)

# Top-level section keys expected inside "startup_evaluation"
_EXPECTED_SECTIONS = set(TARGET_SCHEMA["startup_evaluation"].keys())


# ---------------------------------------------------------------------------
# JSON parsing — 4-tier fallback so the pipeline never crashes on bad output
# ---------------------------------------------------------------------------

def _parse_json(raw: object) -> dict:
    """
    Robustly extract a JSON dict from an LLM response.

    Tries in order:
      1. Already a dict (ModalCustomLLM json_mode path) → return as-is.
      2. Direct json.loads on the full string.
      3. Strip markdown fences (```json ... ```) then json.loads.
      4. Regex: find the outermost { ... } block and parse it.
      5. Fallback: log a warning and return a clean empty TARGET_SCHEMA scaffold.
    """
    # Tier 1 — already parsed upstream
    if isinstance(raw, dict):
        return raw

    text = raw.strip() if isinstance(raw, str) else ""

    # Tier 2 — direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # Tier 3 — strip markdown fences
    fenced = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    fenced = re.sub(r"\s*```$", "", fenced).strip()
    try:
        return json.loads(fenced)
    except (json.JSONDecodeError, ValueError):
        pass

    # Tier 4 — find outermost { ... } block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback — log and return empty scaffold
    logger.warning(
        "[PDF Extractor] Could not parse LLM output as JSON. "
        "Returning empty scaffold. First 300 chars of raw output: %r",
        text[:300],
    )
    return copy.deepcopy(TARGET_SCHEMA)


# ---------------------------------------------------------------------------
# Schema validation and repair
# ---------------------------------------------------------------------------

def _validate_and_repair(raw: dict) -> dict:
    """
    Ensure the parsed dict matches TARGET_SCHEMA structure.

    Steps:
      1. Normalise — wrap bare dict in {"startup_evaluation": ...} if missing.
      2. Schema guard — if the model hallucinated a completely different set of
         keys (none overlap with expected sections), discard and return scaffold.
      3. Prune + merge — copy only known keys into a scaffold deep-copy so
         every missing field keeps its typed default.
    """
    # Step 1 — normalise top-level wrapper
    if "startup_evaluation" not in raw:
        raw = {"startup_evaluation": raw}

    body = raw.get("startup_evaluation", {})

    # Step 2 — schema guard
    returned_keys = set(body.keys()) if isinstance(body, dict) else set()
    if not returned_keys.intersection(_EXPECTED_SECTIONS):
        logger.warning(
            "[PDF Extractor] LLM returned wrong schema keys %s — resetting to empty scaffold.",
            returned_keys,
        )
        return copy.deepcopy(TARGET_SCHEMA)

    # Step 3 — prune unknown keys, merge valid values into scaffold
    scaffold = copy.deepcopy(TARGET_SCHEMA)
    for section in _EXPECTED_SECTIONS:
        if section not in body:
            continue                            # keep scaffold default

        section_val = body[section]
        scaffold_section = scaffold["startup_evaluation"][section]

        if isinstance(scaffold_section, dict) and isinstance(section_val, dict):
            for key in scaffold_section:
                if key in section_val:
                    scaffold["startup_evaluation"][section][key] = section_val[key]
        elif isinstance(scaffold_section, list) and isinstance(section_val, list):
            scaffold["startup_evaluation"][section] = section_val
        # type mismatch → keep scaffold default

    return scaffold


# ---------------------------------------------------------------------------
# LangGraph nodes
# ---------------------------------------------------------------------------

async def extract_text_node(state: PDFExtractorState) -> PDFExtractorState:
    """
    Stage 1 — PDF → plain text.

    Uses a two-tier extractor (PyPDF2 → pymupdf fallback) defined in tools.py.
    """
    file_name = state.get("file_name", "document.pdf")
    logger.info("[PDF Extractor] Extracting text from %s ...", file_name)

    try:
        document_text = extract_text_from_pdf(state["file_bytes"])

        if not document_text.strip():
            return {**state, "error": "PDF contains no extractable text."}

        logger.info(
            "[PDF Extractor] Extracted %d characters from %s.",
            len(document_text),
            file_name,
        )
        return {**state, "document_text": document_text}

    except Exception as exc:
        logger.error("[PDF Extractor] Text extraction failed: %s", exc)
        return {**state, "error": f"Could not read PDF text: {exc}"}


async def llm_extraction_node(state: PDFExtractorState) -> PDFExtractorState:
    """
    Stage 2 — plain text → raw structured dict via fine-tuned Gemma 3n.

    Key fix: uses StrOutputParser (already imported, never crashes) and
    delegates all JSON parsing to _parse_json() which has 4 fallback tiers.
    JsonOutputParser is intentionally NOT used here — it throws
    OUTPUT_PARSING_FAILURE on any imperfect model output with no recovery path.
    """
    if state.get("error"):
        return state

    logger.info("[PDF Extractor] Requesting LLM extraction...")

    try:
        # temperature=0 for deterministic structured output
        llm = get_llm(temperature=0, provider="modal")

        # StrOutputParser — returns raw string, never crashes on bad JSON
        chain = PromptTemplate.from_template(PDF_EXTRACTION_PROMPT) | llm | StrOutputParser()

        raw_string: str = await chain.ainvoke({
            "target_schema": json.dumps(TARGET_SCHEMA, indent=2),
            "document_text": state["document_text"],
        })

        # Always log the raw output so you can diagnose fine-tune quality
        logger.info(
            "[PDF Extractor] Raw LLM output (first 400 chars): %r",
            raw_string[:400] if isinstance(raw_string, str) else raw_string,
        )

        # Parse with our own robust 4-tier parser — never LangChain's brittle one
        raw_extracted = _parse_json(raw_string)

        logger.info(
            "[PDF Extractor] Parsed keys: %s",
            list(raw_extracted.keys()) if isinstance(raw_extracted, dict) else type(raw_extracted),
        )
        return {**state, "raw_extracted_data": raw_extracted}

    except Exception as exc:
        logger.error("[PDF Extractor] LLM extraction failed: %s", exc)
        return {**state, "error": f"AI extraction failed: {exc}"}


async def sanitize_data_node(state: PDFExtractorState) -> PDFExtractorState:
    """
    Stage 3 — validate schema shape, coerce numeric types.

    Runs even when raw_extracted_data is a fallback scaffold — the output is
    always a complete, correctly-typed dict matching TARGET_SCHEMA.
    """
    if state.get("error"):
        return state

    logger.info("[PDF Extractor] Sanitizing extracted data...")

    try:
        raw_extracted = state["raw_extracted_data"]

        # Validate structure; repair / reset to scaffold if model hallucinated
        validated = _validate_and_repair(raw_extracted)

        # Coerce numeric fields: "$500k" / "USD 0" / None → int / float
        sanitized_data = force_numeric_types(validated)

        logger.info(
            "[PDF Extractor] Sanitization complete for: %s",
            state.get("file_name", "document"),
        )
        return {**state, "sanitized_data": sanitized_data}

    except Exception as exc:
        logger.error("[PDF Extractor] Data sanitization failed: %s", exc)
        return {**state, "error": f"Data sanitization failed: {exc}"}