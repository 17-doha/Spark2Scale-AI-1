from fastapi import APIRouter, HTTPException, UploadFile, File
from app.core.logger import get_logger
from app.graph.pdf_extractor import pdf_extractor_app

router = APIRouter()
logger = get_logger(__name__)

# =========================================================
# PDF EXTRACTION ENDPOINT
# =========================================================

@router.post("/extract-from-pdf")
async def extract_from_pdf(file: UploadFile = File(...)):
    """
    Extracts startup data from PDF and ensures numeric fields are integers/floats.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    try:
        file_bytes = await file.read()
        
        # Invoke the new PDF Extractor graph
        inputs = {
            "file_bytes": file_bytes,
            "file_name": file.filename
        }
        
        result = await pdf_extractor_app.ainvoke(inputs)
        
        if result.get("error"):
            raise Exception(result["error"])
            
        sanitized_data = result.get("sanitized_data", {})

        logger.info(f"[SUCCESS] Extracted and sanitized data from: {file.filename}")
        return {"data": sanitized_data}

    except Exception as e:
        logger.error(f"[ERROR] PDF processing/extraction failed: {e}")
        # Determine appropriate status code
        status_code = 422 if "Could not read PDF" in str(e) or "no extractable text" in str(e) else 500
        raise HTTPException(status_code=status_code, detail=str(e))