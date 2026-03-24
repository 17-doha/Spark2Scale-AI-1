import json
import io
import re
from fastapi import APIRouter, HTTPException, UploadFile, File
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from app.core.llm import get_llm
from app.core.logger import get_logger
from app.graph.evaluation_agent.prompts.general_prompts import PDF_EXTRACTION_PROMPT
from app.graph.evaluation_agent.helpers import TARGET_SCHEMA

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

router = APIRouter()
logger = get_logger(__name__)

# --- Helper: Data Sanitizer ---
def force_numeric_types(data: any):
    """
    Recursively ensures fields that should be numbers are actually numbers.
    Prevents '>' errors between str and int.
    """
    numeric_fields = {
        "amount_raised_to_date", "target_amount", "ownership_percentage", 
        "years_direct_experience", "interviews_conducted", "user_count", 
        "active_users_monthly", "early_revenue", "growth_rate", 
        "average_price_per_customer", "gross_margin", "monthly_burn", "runway_months"
    }
    
    if isinstance(data, dict):
        for key, value in data.items():
            if key in numeric_fields:
                if isinstance(value, str):
                    # Remove everything except digits and decimal points
                    clean_val = re.sub(r'[^0-9.]', '', value)
                    try:
                        data[key] = float(clean_val) if '.' in clean_val else int(clean_val)
                    except ValueError:
                        data[key] = 0
                elif value is None:
                    data[key] = 0
            else:
                force_numeric_types(value)
    elif isinstance(data, list):
        for item in data:
            force_numeric_types(item)
    return data

def extract_text_from_pdf(file_bytes: bytes) -> str:
    if PdfReader is None:
        raise ImportError("PyPDF2 is not installed. Run: pip install PyPDF2")
    reader = PdfReader(io.BytesIO(file_bytes))
    pages_text = [p.extract_text() for p in reader.pages if p.extract_text()]
    return "\n\n".join(pages_text)

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

    # 1. Read & Extract
    try:
        file_bytes = await file.read()
        document_text = extract_text_from_pdf(file_bytes)
    except Exception as e:
        logger.error(f"[ERROR] PDF processing failed: {e}")
        raise HTTPException(status_code=422, detail="Could not read PDF text.")

    if not document_text.strip():
        raise HTTPException(status_code=422, detail="PDF contains no extractable text.")

    # 2. Prepare LLM Chain
    # We use Gemini for the large context window
    llm = get_llm(temperature=0, provider="gemini")
    chain = PromptTemplate.from_template(PDF_EXTRACTION_PROMPT) | llm | JsonOutputParser()

    try:
        # 3. Invoke LLM
        # Note: We pass the TARGET_SCHEMA as a string for context
        raw_extracted = await chain.ainvoke({
            "target_schema": json.dumps(TARGET_SCHEMA, indent=2),
            "document_text": document_text
        })

        # 4. Post-Process & Sanitize
        # Ensure the top-level key exists
        extracted_data = raw_extracted if "startup_evaluation" in raw_extracted else {"startup_evaluation": raw_extracted}
        
        # CRITICAL: Convert "USD 0" -> 0 to prevent downstream crashes
        sanitized_data = force_numeric_types(extracted_data)

        logger.info(f"[SUCCESS] Extracted and sanitized data from: {file.filename}")
        return {"data": sanitized_data}

    except Exception as e:
        logger.error(f"[ERROR] LLM extraction failed: {e}")
        raise HTTPException(status_code=500, detail=f"AI extraction failed: {str(e)}")