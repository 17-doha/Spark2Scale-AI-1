import json
import io
from fastapi import APIRouter, HTTPException, UploadFile, File
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from app.core.llm import get_llm
from app.core.logger import get_logger
from app.graph.evaluation_agent.prompts.prompts import PDF_EXTRACTION_PROMPT
from app.graph.evaluation_agent.helpers import TARGET_SCHEMA

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

router = APIRouter()
logger = get_logger(__name__)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Extracts all text from a PDF file given its raw bytes.
    """
    if PdfReader is None:
        raise ImportError("PyPDF2 is not installed. Run: pip install PyPDF2")

    reader = PdfReader(io.BytesIO(file_bytes))
    pages_text = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages_text.append(text)

    return "\n\n".join(pages_text)

@router.post("/extract-from-pdf")
async def extract_from_pdf(file: UploadFile = File(...)):
    """
    Accepts a PDF document and returns the startup evaluation schema
    filled ONLY with information explicitly found in the document.
    """
    # 1. Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are accepted. Please upload a .pdf file."
        )

    # 2. Read PDF bytes
    try:
        file_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read uploaded file: {str(e)}")

    # 3. Extract text from PDF
    try:
        document_text = extract_text_from_pdf(file_bytes)
    except Exception as e:
        logger.error(f"❌ PDF text extraction failed: {e}")
        raise HTTPException(status_code=422, detail=f"Failed to extract text from PDF: {str(e)}")

    if not document_text.strip():
        raise HTTPException(
            status_code=422,
            detail="The PDF appears to contain no extractable text (it may be a scanned image)."
        )

    logger.info(f"📄 Extracted {len(document_text)} characters from PDF: {file.filename}")

    # 4. Use LLM to fill the schema from the document text
    #    Using Gemini for larger context window (PDFs can be long)
    llm = get_llm(temperature=0, provider="gemini")

    chain = PromptTemplate.from_template(PDF_EXTRACTION_PROMPT) | llm | JsonOutputParser()

    try:
        extracted_data = await chain.ainvoke({
            "target_schema": json.dumps(TARGET_SCHEMA, indent=2),
            "document_text": document_text
        })

        # Ensure proper wrapping
        if "startup_evaluation" not in extracted_data:
            extracted_data = {"startup_evaluation": extracted_data}

        logger.info(f"✅ Successfully extracted schema from PDF: {file.filename}")

        return {"data": extracted_data}

    except Exception as e:
        logger.error(f"❌ LLM extraction failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"AI extraction failed: {str(e)}"
        )
