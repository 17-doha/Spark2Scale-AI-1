import os
import time
import json
import tempfile
import shutil
from typing import List, Optional
import uuid

from fastapi import APIRouter, HTTPException, status, File, UploadFile, Form
from pydantic import BaseModel, Field

from app.graph.ppt_generation_agent import app_graph
from app.graph.ppt_generation_agent.state import PPTGenerationState
from app.graph.ppt_generation_agent.tools.ppt_tools import generate_pptx_file
from app.graph.ppt_generation_agent.tools.pptx_parser import extract_text_from_pptx
from app.core.logger import get_logger
from app.core.supabase_client import supabase

logger = get_logger(__name__)
router = APIRouter()

class PPTInput(BaseModel):
    startup_id: str = Field(..., description="The UUID of the startup")
    research_data: Optional[dict] = None
    startup_info: Optional[dict] = None
    market_research: Optional[dict] = None
    logo_path: Optional[str] = None
    color_palette: Optional[List[str]] = None
    use_default_colors: bool = True

    def __init__(self, **data):
        if not data.get("research_data") and (data.get("startup_info") or data.get("market_research")):
            data["research_data"] = {
                "startup_info": data.get("startup_info"),
                "market_research": data.get("market_research")
            }
        super().__init__(**data)

class PPTGenerationResponse(BaseModel):
    status: str
    ppt_path: Optional[str]
    title: Optional[str]
    iterations: Optional[int]
    message: Optional[str]
    json_response: Optional[dict] = None

async def run_ppt_generation(state: PPTGenerationState, startup_id: str) -> "PPTGenerationResponse":
    try:
        final_state = await app_graph.ainvoke(state)
        final_draft = final_state.get("draft")
        if not final_draft:
            raise HTTPException(status_code=500, detail="Draft generation failed.")

        output_dir = os.path.join("output", "ppt_generation", f"ppt{startup_id}")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{startup_id}.pptx")

        local_path = await generate_pptx_file(final_draft, output_path)

        # ── Upload to Supabase Storage: {startup_id}/ppts/{filename} ──
        storage_path = local_path  # fallback
        if supabase:
            try:
                file_name = f"{uuid.uuid4().hex}.pptx"
                supabase_storage_path = f"{startup_id}/{file_name}"

                with open(local_path, "rb") as f:
                    supabase.storage.from_("ppts").upload(
                        path=supabase_storage_path,
                        file=f,
                        file_options={"content-type": "application/vnd.openxmlformats-officedocument.presentationml.presentation", "upsert": "true"}
                    )

                storage_path = supabase.storage.from_("ppts").get_public_url(supabase_storage_path)

                doc_data = {
                    "startup_id": startup_id,
                    "document_name": final_draft.title,
                    "type": "PPT",          # ← fixed
                    "current_path": storage_path,
                    "json_response": final_draft.model_dump()
                }
                supabase.table("documents").insert(doc_data).execute()
                logger.info("Successfully pushed metadata to Supabase")
            except Exception as e:
                logger.error(f"Supabase error: {e}")

        return PPTGenerationResponse(
            status="success",
            ppt_path=storage_path,
            title=final_draft.title,
            iterations=final_state.get("iteration", 0),
            message="Presentation generated successfully",
            json_response=final_draft.model_dump()
        )
    except Exception as e:
        logger.error(f"Error in PPT generation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate", response_model=PPTGenerationResponse)
async def generate_ppt(input_data: PPTInput): 
    """Generate from JSON body."""
    initial_state: PPTGenerationState = {
        "research_data": input_data.research_data,
        "logo_path": input_data.logo_path,
        "color_palette": input_data.color_palette,
        "use_default_colors": input_data.use_default_colors,
        "draft": None,
        "critique": None,
        "iteration": 0,
        "ppt_path": None,
    }
    return await run_ppt_generation(initial_state, input_data.startup_id)

@router.post("/generate/upload", response_model=PPTGenerationResponse)
async def generate_ppt_from_files(
    startup_id: str = Form(..., description="The UUID of the startup"),
    startup_info_file: UploadFile = File(..., description="Startup info JSON file"),
    market_research_file: UploadFile = File(..., description="Market research JSON file"),
    logo: Optional[UploadFile] = File(None),
    use_default_colors: bool = Form(True)
):
    """Generate by uploading JSON files and an optional logo."""
    temp_dir = tempfile.mkdtemp()
    try:
        # Load and merge JSON content
        si_content = json.loads(await startup_info_file.read())
        mr_content = json.loads(await market_research_file.read())
        
        research_data = {
            "startup_info": si_content,
            "market_research": mr_content
        }

        # Handle logo if provided
        logo_path = None
        if logo:
            logo_path = os.path.join(temp_dir, logo.filename)
            with open(logo_path, "wb") as f:
                f.write(await logo.read())

        initial_state: PPTGenerationState = {
            "research_data": research_data,
            "logo_path": logo_path,
            "color_palette": None,
            "use_default_colors": use_default_colors,
            "draft": None,
            "critique": None,
            "iteration": 0,
            "ppt_path": None,
        }

        return await run_ppt_generation(initial_state, startup_id)

    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

@router.post("/edit", response_model=PPTGenerationResponse)
async def edit_ppt(
    startup_id: str = Form(..., description="The UUID of the startup"),
    ppt_file: UploadFile = File(..., description="The existing PPTX file to edit"),
    logo: Optional[UploadFile] = File(None),
    use_default_colors: bool = Form(True)
):
    """Refine an existing PPTX file to match pitch standards."""
    temp_dir = tempfile.mkdtemp()
    try:
        # Save uploaded PPTX
        pptx_path = os.path.join(temp_dir, ppt_file.filename)
        with open(pptx_path, "wb") as f:
            f.write(await ppt_file.read())
        
        # Extract structured text
        extracted_text = extract_text_from_pptx(pptx_path)
        if not extracted_text:
            raise HTTPException(status_code=400, detail="Could not extract text from the provided PPTX.")

        logo_path = None
        if logo:
            logo_path = os.path.join(temp_dir, logo.filename)
            with open(logo_path, "wb") as f:
                f.write(await logo.read())

        initial_state: PPTGenerationState = {
            "research_data": extracted_text,
            "logo_path": logo_path,
            "color_palette": None,
            "use_default_colors": use_default_colors,
            "draft": None,
            "critique": None,
            "iteration": 0,
            "ppt_path": pptx_path,
            "mode": "edit"
        }

        return await run_ppt_generation(initial_state, startup_id)

    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)