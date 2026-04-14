import os
import logging

from fastapi import APIRouter, HTTPException

from app.graph.document_chat.schema import DocumentQARequest, DocumentQAResponse
from app.graph.document_chat.workflow import app as document_chat_graph

logger = logging.getLogger(__name__)

router = APIRouter()

# Security constraint: 10 MB limit for text/JSON/PPTX processing
MAX_FILE_SIZE_MB = 10


@router.post("/test-document-qa", response_model=DocumentQAResponse)
async def test_document_qa(request: DocumentQARequest):
    """
    Document context extraction and QA pipeline powered by the
    document_chat LangGraph workflow.

    Steps (handled internally by the graph):
      1. parse_document_node  — parse file / payload, sanitise PII, cap query.
      2. answer_query_node    — invoke the LangChain QA chain and return the answer.
    """
    # --- Guardrail: file must exist on disk ---
    if not os.path.exists(request.file_path):
        logger.error(f"File not found at path: {request.file_path}")
        raise HTTPException(
            status_code=404,
            detail=f"File not found at path: {request.file_path}",
        )

    # --- Guardrail: cap file size to prevent container memory overflow ---
    file_size_bytes = os.path.getsize(request.file_path)
    if file_size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024:
        logger.warning(
            f"Rejected file {request.file_path}: exceeds {MAX_FILE_SIZE_MB} MB limit."
        )
        raise HTTPException(
            status_code=413,
            detail=f"Payload Too Large. Maximum allowed file size is {MAX_FILE_SIZE_MB} MB.",
        )

    try:
        logger.info(
            f"Invoking document_chat graph | file={request.file_path!r} "
            f"provider={request.provider!r}"
        )

        initial_state = {
            "file_path": request.file_path,
            "query": request.query,
            "provider": request.provider,
            "model_name": request.model_name,
        }

        result = document_chat_graph.invoke(initial_state)

        return DocumentQAResponse(
            status="success",
            provider_used=request.provider,
            query=result["query"],   # may have been sanitised by the graph
            answer=result["answer"],
        )

    except ValueError as e:
        logger.error(f"Parsing error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Inference error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred during inference: {e}",
        )