from typing import TypedDict, Optional, Dict, Any

class PDFExtractorState(TypedDict):
    # Inputs
    file_bytes: bytes
    file_name: str
    
    # Intermediate
    document_text: str
    raw_extracted_data: Dict[str, Any]
    
    # Outputs
    sanitized_data: Dict[str, Any]
    error: Optional[str]
