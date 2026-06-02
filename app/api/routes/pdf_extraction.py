from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from app.core.logger import get_logger
from app.core.auth import get_current_user
from app.graph.pdf_extractor.workflow import pdf_extractor_app

router = APIRouter()
logger = get_logger(__name__)

_MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB
_PDF_MAGIC = b"%PDF"


@router.post("/extract-from-pdf")
async def extract_from_pdf(file: UploadFile = File(...), current_user=Depends(get_current_user)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    try:
        file_bytes = await file.read()

        if len(file_bytes) > _MAX_PDF_BYTES:
            raise HTTPException(status_code=413, detail="File too large. Maximum allowed size is 20 MB.")

        if not file_bytes.startswith(_PDF_MAGIC):
            raise HTTPException(status_code=400, detail="File does not appear to be a valid PDF.")

        result = await pdf_extractor_app.ainvoke({
            "file_bytes": file_bytes,
            "file_name": file.filename,
        })

        if result.get("error"):
            error_msg = result["error"]
            logger.error("[PDF Endpoint] Pipeline error: %s", error_msg)
            if any(kw in error_msg for kw in ("Could not read PDF", "no extractable text", "extract text")):
                raise HTTPException(status_code=422, detail=error_msg)
            raise HTTPException(status_code=500, detail="PDF processing failed. Please try again.")

        sanitized_data = result.get("sanitized_data", {})
        logger.info("[PDF Endpoint] Success: %s", file.filename)
        return {"data": sanitized_data}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[PDF Endpoint] Unexpected error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")
