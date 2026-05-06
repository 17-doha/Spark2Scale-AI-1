from fastapi import APIRouter, HTTPException, UploadFile, File

from app.core.logger import get_logger
from app.graph.pdf_extractor.workflow import pdf_extractor_app

router = APIRouter()
logger = get_logger(__name__)


@router.post("/extract-from-pdf")
async def extract_from_pdf(file: UploadFile = File(...)):
    """
    Accept a PDF pitch deck and return structured startup evaluation data
    matching TARGET_SCHEMA.

    Pipeline (3 LangGraph nodes):
      1. extract_text   — PyPDF2 → pymupdf fallback
      2. llm_extraction — Gemma 3n (Modal) with StrOutputParser + 4-tier JSON parser
      3. sanitize_data  — schema validation, numeric coercion

    Returns
    -------
    {"data": <TARGET_SCHEMA-shaped dict>}

    Error codes
    -----------
    400 — not a PDF file
    422 — PDF has no extractable text (unreadable / blank)
    500 — LLM or sanitization failure
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    try:
        file_bytes = await file.read()

        result = await pdf_extractor_app.ainvoke({
            "file_bytes": file_bytes,
            "file_name": file.filename,
        })

        if result.get("error"):
            error_msg = result["error"]
            logger.error("[PDF Endpoint] Pipeline error: %s", error_msg)

            # Differentiate unreadable PDFs (client error) from model failures (server error)
            if any(kw in error_msg for kw in ("Could not read PDF", "no extractable text", "extract text")):
                raise HTTPException(status_code=422, detail=error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

        sanitized_data = result.get("sanitized_data", {})
        logger.info("[PDF Endpoint] Success: %s", file.filename)
        return {"data": sanitized_data}

    except HTTPException:
        raise    # re-raise FastAPI exceptions unchanged
    except Exception as exc:
        logger.error("[PDF Endpoint] Unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))