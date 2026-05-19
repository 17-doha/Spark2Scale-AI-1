import os
import logging
import tempfile
import json
import requests

from fastapi import APIRouter, HTTPException

from app.graph.document_chat.schema import DocumentQARequest, DocumentQAResponse
from app.graph.document_chat.workflow import app as document_chat_graph

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_FILE_SIZE_MB = 10

def is_valid_json(data: str) -> bool:
    """Helper to check if a string is valid JSON."""
    try:
        json.loads(data)
        return True
    except ValueError:
        return False

@router.post("/test-document-qa", response_model=DocumentQAResponse)
async def test_document_qa(request: DocumentQARequest):
    """
    Document context extraction and QA pipeline powered by the
    document_chat LangGraph workflow.
    """
    actual_file_path = request.file_path
    is_temp_file = False

    try:
        # --- PRE-PROCESSING: Handle URLs and JSON Strings ---
        if actual_file_path.startswith(("http://", "https://")):
            try:
                logger.info(f"Downloading file from URL: {actual_file_path}")
                response = requests.get(actual_file_path, timeout=15)
                response.raise_for_status()
                
                # Save to a temporary file
                fd, temp_path = tempfile.mkstemp(suffix=".pdf") 
                with os.fdopen(fd, 'wb') as f:
                    f.write(response.content)
                
                actual_file_path = temp_path
                is_temp_file = True
            except Exception as e:
                logger.error(f"Failed to download URL: {e}")
                raise HTTPException(status_code=400, detail=f"Could not download file from URL: {e}")

        elif actual_file_path.strip().startswith(("{", "[")) and is_valid_json(actual_file_path):
            try:
                logger.info("Processing raw JSON string payload.")
                fd, temp_path = tempfile.mkstemp(suffix=".json")
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write(actual_file_path)
                
                actual_file_path = temp_path
                is_temp_file = True
            except Exception as e:
                logger.error(f"Failed to parse JSON string: {e}")
                raise HTTPException(status_code=400, detail=f"Failed to process JSON payload: {e}")

        # --- Guardrail: file must exist on disk ---
        if not os.path.exists(actual_file_path):
            logger.error(f"File not found at path: {actual_file_path}")
            raise HTTPException(
                status_code=404,
                detail=f"File not found at path: {actual_file_path}",
            )

        # --- Guardrail: cap file size ---
        file_size_bytes = os.path.getsize(actual_file_path)
        if file_size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024:
            logger.warning(f"Rejected file {actual_file_path}: exceeds {MAX_FILE_SIZE_MB} MB limit.")
            raise HTTPException(
                status_code=413,
                detail=f"Payload Too Large. Maximum allowed file size is {MAX_FILE_SIZE_MB} MB.",
            )

        # --- GRAPH INVOCATION ---
        logger.info(
            f"Invoking document_chat graph | file={actual_file_path!r} "
            f"provider={request.provider!r}"
        )

        initial_state = {
            "file_path": actual_file_path,
            "query": request.query,
            "provider": request.provider,
            "model_name": request.model_name,
            "chat_history": request.chat_history or [],
            "document_type": request.document_type or None,
        }

        result = await document_chat_graph.ainvoke(initial_state)

        return DocumentQAResponse(
            status="success",
            provider_used=request.provider,
            query=result["query"],   
            answer=result["answer"],
        )

    except HTTPException:
        raise  
    except ValueError as e:
        logger.error(f"Parsing error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Inference error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred during inference: {e}",
        )
    finally:
        # --- CLEANUP ---
        if is_temp_file and actual_file_path and os.path.exists(actual_file_path):
            try:
                os.remove(actual_file_path)
                logger.info(f"Cleaned up temporary file: {actual_file_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary file {actual_file_path}: {e}")