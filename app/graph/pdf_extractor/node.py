import json
import re
import copy

from langchain_core.output_parsers import StrOutputParser

from app.core.llm import get_llm, _PROMPT_PASSTHROUGH_PREFIX
from app.core.logger import get_logger
from app.graph.pdf_extractor.state import PDFExtractorState
from app.graph.pdf_extractor.tools import extract_text_from_pdf, force_numeric_types
from app.graph.pdf_extractor.schema import TARGET_SCHEMA

logger = get_logger(__name__)

_EXPECTED_SECTIONS = set(TARGET_SCHEMA["startup_evaluation"].keys())

# ---------------------------------------------------------------------------
# Token budget constants (must match modal_deploy.py)
# ---------------------------------------------------------------------------
_MAX_MODEL_LEN  = 8192
_MAX_NEW_TOKENS = 1024
_SAFETY_MARGIN  = 128
# How many tokens we can spend on the document text
# = window  - output reservation - safety - schema overhead - instruction overhead
# Schema JSON ≈ 600 tokens, instructions ≈ 200 tokens → overhead ≈ 900
_INSTRUCTION_SCHEMA_OVERHEAD = 900
_DOC_TOKEN_BUDGET = (
    _MAX_MODEL_LEN - _MAX_NEW_TOKENS - _SAFETY_MARGIN - _INSTRUCTION_SCHEMA_OVERHEAD
)  # ≈ 6060 tokens — plenty for most pitch decks


# ---------------------------------------------------------------------------
# Prompt builder
#
# Document text comes BEFORE the schema so head-truncation on the Modal side
# never silently drops the content the model needs to read.
#
# Layout:
#   <instructions>
#   <document text>          ← preserved by head truncation
#   <schema>                 ← can be partially cut; model knows it from fine-tune
#   <fill instruction>
# ---------------------------------------------------------------------------

def _build_extraction_prompt(document_text: str) -> str:
    """
    Build the extraction prompt with document text BEFORE the schema.
    This ensures the Modal truncation (which keeps the HEAD) never silently
    drops the PDF content — it can only trim the schema tail, which is less
    critical since the model learned the schema structure during fine-tuning.
    """
    schema_str = json.dumps(TARGET_SCHEMA, indent=2)

    return (
        "You are a strict JSON data extractor for startup pitch documents.\n\n"
        "=== YOUR ONLY JOB ===\n"
        "Read the DOCUMENT TEXT below and populate the TARGET SCHEMA with information "
        "that is EXPLICITLY stated in the document.\n\n"
        "=== HARD RULES ===\n"
        "1. OUTPUT STRUCTURE: Your entire response MUST be a single JSON object "
        "matching the TARGET SCHEMA — same keys, same nesting, same types.\n"
        "2. ONLY EXPLICIT DATA: Fill a field ONLY if that exact information is "
        "written in the document. If not found:\n"
        "   - Strings  → \"\"\n"
        "   - Numbers  → 0\n"
        "   - Arrays   → []\n"
        "3. CURRENCY: Strip symbols. \"$500,000\" → 500000.\n"
        "4. DATES: Use YYYY-MM-DD format.\n"
        "5. JSON ONLY: Output MUST start with { and end with }. "
        "No markdown, no explanation.\n\n"
        "=== DOCUMENT TEXT ===\n"
        + document_text
        + "\n\n=== TARGET SCHEMA ===\n"
        + schema_str
        + "\n\n=== OUTPUT ===\n"
        "Fill every field from the document above and return the JSON object now:\n"
    )


# ---------------------------------------------------------------------------
# Safe character-level truncation of document text
#
# Called BEFORE building the prompt so the schema is never touched.
# Rough heuristic: 1 token ≈ 4 chars for English text.
# ---------------------------------------------------------------------------

def _truncate_document_text(document_text: str) -> str:
    """
    Trim the document text to fit within _DOC_TOKEN_BUDGET before it is
    embedded in the prompt. We keep the HEAD of the document (title, company
    name, executive summary) which contains the fields most commonly missing.
    """
    CHARS_PER_TOKEN = 4
    max_chars = _DOC_TOKEN_BUDGET * CHARS_PER_TOKEN

    if len(document_text) <= max_chars:
        return document_text

    trimmed = document_text[:max_chars]
    logger.warning(
        "[PDF Extractor] Document text truncated from %d to %d chars "
        "(≈%d tokens) to fit model window.",
        len(document_text), max_chars, _DOC_TOKEN_BUDGET,
    )
    return trimmed


# ---------------------------------------------------------------------------
# JSON parsing — 4-tier fallback
# ---------------------------------------------------------------------------

def _parse_json(raw: object) -> dict:
    if isinstance(raw, dict):
        return raw

    text = raw.strip() if isinstance(raw, str) else ""

    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    fenced = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    fenced = re.sub(r"\s*```$", "", fenced).strip()
    try:
        return json.loads(fenced)
    except (json.JSONDecodeError, ValueError):
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except (json.JSONDecodeError, ValueError):
            pass

    logger.warning(
        "[PDF Extractor] Could not parse LLM output as JSON. "
        "First 300 chars of raw output: %r",
        text[:300],
    )
    return copy.deepcopy(TARGET_SCHEMA)


# ---------------------------------------------------------------------------
# Schema validation and repair
# ---------------------------------------------------------------------------

def _validate_and_repair(raw: dict) -> dict:
    if "startup_evaluation" not in raw:
        raw = {"startup_evaluation": raw}

    body = raw.get("startup_evaluation", {})
    returned_keys = set(body.keys()) if isinstance(body, dict) else set()

    if not returned_keys.intersection(_EXPECTED_SECTIONS):
        logger.warning(
            "[PDF Extractor] Wrong schema keys returned: %s — resetting to scaffold.",
            returned_keys,
        )
        return copy.deepcopy(TARGET_SCHEMA)

    scaffold = copy.deepcopy(TARGET_SCHEMA)
    for section in _EXPECTED_SECTIONS:
        if section not in body:
            continue
        section_val      = body[section]
        scaffold_section = scaffold["startup_evaluation"][section]

        if isinstance(scaffold_section, dict) and isinstance(section_val, dict):
            for key in scaffold_section:
                if key in section_val:
                    scaffold["startup_evaluation"][section][key] = section_val[key]
        elif isinstance(scaffold_section, list) and isinstance(section_val, list):
            scaffold["startup_evaluation"][section] = section_val

    return scaffold


# ---------------------------------------------------------------------------
# LangGraph nodes
# ---------------------------------------------------------------------------

async def extract_text_node(state: PDFExtractorState) -> PDFExtractorState:
    file_name = state.get("file_name", "document.pdf")
    logger.info("[PDF Extractor] Extracting text from %s ...", file_name)

    try:
        document_text = extract_text_from_pdf(state["file_bytes"])
        if not document_text.strip():
            return {**state, "error": "PDF contains no extractable text."}

        logger.info(
            "[PDF Extractor] Extracted %d chars from %s.",
            len(document_text), file_name,
        )
        return {**state, "document_text": document_text}

    except Exception as exc:
        logger.error("[PDF Extractor] Text extraction failed: %s", exc)
        return {**state, "error": f"Could not read PDF text: {exc}"}


async def llm_extraction_node(state: PDFExtractorState) -> PDFExtractorState:
    if state.get("error"):
        return state

    logger.info("[PDF Extractor] Requesting LLM extraction...")

    try:
        llm = get_llm(temperature=0, provider="gemini")

        # 1. Trim document text BEFORE building the prompt
        #    so the schema is never touched by truncation.
        doc_text = _truncate_document_text(state["document_text"])

        logger.info(
            "[PDF Extractor] Document text after truncation: %d chars. "
            "First 300: %r",
            len(doc_text), doc_text[:300],
        )

        # 2. Build prompt with doc text BEFORE schema
        prompt_text = _PROMPT_PASSTHROUGH_PREFIX + _build_extraction_prompt(doc_text)

        logger.info(
            "[PDF Extractor] Total prompt length: %d chars. "
            "Last 200 chars (should be schema tail + fill instruction): %r",
            len(prompt_text),
            prompt_text[-200:],
        )

        # 3. Call model
        raw_string: str = await (llm | StrOutputParser()).ainvoke(prompt_text)

        logger.info(
            "[PDF Extractor] Raw LLM output (%d chars). First 800: %r",
            len(raw_string) if isinstance(raw_string, str) else -1,
            raw_string[:800] if isinstance(raw_string, str) else raw_string,
        )

        raw_extracted = _parse_json(raw_string)
        return {**state, "raw_extracted_data": raw_extracted}

    except Exception as exc:
        logger.error("[PDF Extractor] LLM extraction failed: %s", exc, exc_info=True)
        return {**state, "error": f"AI extraction failed: {exc}"}


async def sanitize_data_node(state: PDFExtractorState) -> PDFExtractorState:
    if state.get("error"):
        return state

    logger.info("[PDF Extractor] Sanitizing extracted data...")

    try:
        validated      = _validate_and_repair(state["raw_extracted_data"])
        sanitized_data = force_numeric_types(validated)

        logger.info(
            "[PDF Extractor] Sanitization complete for: %s",
            state.get("file_name", "document"),
        )
        return {**state, "sanitized_data": sanitized_data}

    except Exception as exc:
        logger.error("[PDF Extractor] Data sanitization failed: %s", exc)
        return {**state, "error": f"Data sanitization failed: {exc}"}