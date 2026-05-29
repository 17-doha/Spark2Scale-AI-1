from typing import TypedDict, Optional, Dict, Any


class PDFExtractorState(TypedDict):
    # ── Inputs ────────────────────────────────────────────────────────────────
    file_bytes: bytes
    file_name: str

    # ── Intermediate ──────────────────────────────────────────────────────────
    document_text: str          # raw text from PDF (Stage 1 output)
    raw_extracted_data: Dict[str, Any]  # parsed dict from LLM (Stage 2 output)

    # ── Outputs ───────────────────────────────────────────────────────────────
    sanitized_data: Dict[str, Any]  # final clean dict matching TARGET_SCHEMA
    error: Optional[str]            # set by any node on failure; short-circuits pipeline