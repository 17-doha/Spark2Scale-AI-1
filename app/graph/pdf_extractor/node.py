import json
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from app.core.llm import get_llm
from app.core.logger import get_logger
from app.graph.pdf_extractor.state import PDFExtractorState
from app.graph.pdf_extractor.tools import extract_text_from_pdf, force_numeric_types
from app.graph.pdf_extractor.prompts import PDF_EXTRACTION_PROMPT
from app.graph.pdf_extractor.schema import TARGET_SCHEMA

logger = get_logger(__name__)

async def extract_text_node(state: PDFExtractorState) -> PDFExtractorState:
    logger.info(f"[PDF Extractor] Extracting text from {state.get('file_name', 'document.pdf')}...")
    
    try:
        file_bytes = state["file_bytes"]
        document_text = extract_text_from_pdf(file_bytes)
        
        if not document_text.strip():
            return {**state, "error": "PDF contains no extractable text."}
            
        return {**state, "document_text": document_text}
    except Exception as e:
        logger.error(f"[ERROR] PDF processing failed: {e}")
        return {**state, "error": f"Could not read PDF text: {str(e)}"}

async def llm_extraction_node(state: PDFExtractorState) -> PDFExtractorState:
    if state.get("error"):
        return state
        
    logger.info("[PDF Extractor] Requesting LLM extraction...")
    
    try:
        # We use Gemini for the large context window
        llm = get_llm(temperature=0, provider="gemini")
        chain = PromptTemplate.from_template(PDF_EXTRACTION_PROMPT) | llm | JsonOutputParser()

        raw_extracted = await chain.ainvoke({
            "target_schema": json.dumps(TARGET_SCHEMA, indent=2),
            "document_text": state["document_text"]
        })
        
        return {**state, "raw_extracted_data": raw_extracted}
    except Exception as e:
        logger.error(f"[ERROR] LLM extraction failed: {e}")
        return {**state, "error": f"AI extraction failed: {str(e)}"}

async def sanitize_data_node(state: PDFExtractorState) -> PDFExtractorState:
    if state.get("error"):
        return state
        
    logger.info("[PDF Extractor] Sanitizing extracted data...")
    
    try:
        raw_extracted = state["raw_extracted_data"]
        # Ensure the top-level key exists
        extracted_data = raw_extracted if "startup_evaluation" in raw_extracted else {"startup_evaluation": raw_extracted}
        
        # CRITICAL: Convert "USD 0" -> 0 to prevent downstream crashes
        sanitized_data = force_numeric_types(extracted_data)
        
        logger.info(f"[SUCCESS] Extracted and sanitized data from: {state.get('file_name', 'document')}")
        return {**state, "sanitized_data": sanitized_data}
    except Exception as e:
        logger.error(f"[ERROR] Data sanitization failed: {e}")
        return {**state, "error": f"Data sanitization failed: {str(e)}"}
