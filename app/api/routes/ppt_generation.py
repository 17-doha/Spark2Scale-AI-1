import os
import time
import json
import tempfile
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status, File, UploadFile, Form
from pydantic import BaseModel, Field

from app.graph.ppt_generation_agent import app_graph
from app.graph.ppt_generation_agent.state import PPTGenerationState
from app.graph.ppt_generation_agent.tools.ppt_tools import generate_pptx_file
from app.graph.ppt_generation_agent.tools.input_loader import load_input_directory
from app.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Constants
if os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_NAME"):
    OUTPUT_DIR = "/tmp/ppt_output"
else:
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
    OUTPUT_DIR = os.path.join(PROJECT_ROOT, "app/graph/ppt_generation_agent/output")
    
class PPTInput(BaseModel):
    """
    Main API contract. Accepts either a pre-merged `research_data` dict/string
    or the two source JSON objects (`startup_info` and `market_research`).

    This aligns with the input files in `app/graph/ppt_generation_agent/input`.
    """

    # Backwards-compatible merged research data (preferred as dict).
    research_data: Optional[dict] = None

    # Source files (optional) - when both provided they will be merged.
    startup_info: Optional[dict] = None
    market_research: Optional[dict] = None

    # Presentation options
    logo_path: Optional[str] = None
    color_palette: Optional[List[str]] = None
    use_default_colors: bool = True

    @classmethod
    def validate_and_merge(cls, values: dict) -> dict:
        """Helper to ensure `research_data` exists by merging provided parts."""
        # If research_data already provided and is a dict, keep it
        rd = values.get("research_data")
        if rd and isinstance(rd, dict):
            return values

        # Merge startup_info and market_research when available
        si = values.get("startup_info")
        mr = values.get("market_research")
        if si or mr:
            merged = {}
            if si:
                merged["startup_info"] = si
            if mr:
                merged["market_research"] = mr
            values["research_data"] = merged

        return values

    # Use root validator style via __init__ override to keep imports simple
    def __init__(self, **data):
        data = self.validate_and_merge(data)
        super().__init__(**data)


class PPTGenerationResponse(BaseModel):
    """Response model for PPT generation endpoint."""
    status: str = Field(..., description="Status of the generation: 'success' or 'error'")
    ppt_path: Optional[str] = Field(None, description="Path to the generated PPTX file")
    title: Optional[str] = Field(None, description="Title of the presentation")
    iterations: Optional[int] = Field(None, description="Number of iterations used")
    file_size_mb: Optional[float] = Field(None, description="Size of the generated file in MB")
    message: Optional[str] = Field(None, description="Additional message or error details")


async def run_ppt_generation(state: PPTGenerationState, output_path: str) -> "PPTGenerationResponse":
    """Run the graph and save the PPTX file."""
    try:
        # 1) Run the LLM graph to get a PPTDraft
        final_state = await app_graph.ainvoke(state)
        final_draft = final_state.get("draft")
        if not final_draft:
            raise HTTPException(status_code=500, detail="Draft generation failed.")

        # 2) Ensure target directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # 3) Render PPTX with Presenton engine
        await generate_pptx_file(final_draft, output_path)

        # 4) Get file size
        file_size_mb = os.path.getsize(output_path) / (1024 * 1024) if os.path.exists(output_path) else 0

        return PPTGenerationResponse(
            status="success",
            ppt_path=output_path,
            title=final_draft.title,
            iterations=final_state.get("iteration", 0),
            file_size_mb=round(file_size_mb, 2),
            message="Presentation generated successfully"
        )
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg and "RESOURCE_EXHAUSTED" in error_msg:
            logger.warning(f"Gemini Quota Exhausted: {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Gemini API quota exceeded. Please wait 1-2 minutes and try again.",
            )
        logger.error(f"Error in PPT generation: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)


async def generate_deck_from_local_files(output_dir: str):
    """
    Load input from local directory and run PPT generation.
    Used by generate_pitch_deck.py script.
    """
    # Load input data from the standard input directory
    input_dir = os.path.join(PROJECT_ROOT, "app/graph/ppt_generation_agent/input")
    loaded_input = load_input_directory(input_dir)
    
    if not loaded_input or not loaded_input.research_data:
        raise ValueError("No valid input data found in input directory")
    
    # Scan for logo file in input directory
    logo_path = None
    if os.path.isdir(input_dir):
        for filename in os.listdir(input_dir):
            lower_name = filename.lower()
            if lower_name.startswith("logo") and lower_name.endswith((".png", ".jpg", ".jpeg")):
                logo_path = os.path.join(input_dir, filename)
                logger.info(f"Found logo file: {logo_path}")
                break
    
    timestamp = int(time.time())
    output_filename = os.path.join(output_dir, f"presentation_{timestamp}.pptx")
    
    # Create initial state from loaded input (LoadedInput is a dataclass, not a dict)
    initial_state: PPTGenerationState = {
        "research_data": loaded_input.research_data,
        "logo_path": logo_path,
        "color_palette": None,  # TODO: Support color palette from input
        "use_default_colors": not bool(logo_path),  # Use logo colors if logo is provided
        "draft": None,
        "critique": None,
        "iteration": 0,
        "ppt_path": None,
    }
    
    return await run_ppt_generation(initial_state, output_filename)


def merge_json_files(startup_info: dict, market_research: dict) -> str:
    """
    Merge startup info and market research JSON into a single research_data string.
    
    Args:
        startup_info: Dictionary from startup_info.json
        market_research: Dictionary from market_research.json
    
    Returns:
        Merged JSON as string
    """
    merged_data = {
        "startup_info": startup_info,
        "market_research": market_research
    }
    return json.dumps(merged_data, indent=2)


async def save_upload_file(upload_file: UploadFile, temp_dir: str) -> str:
    """
    Save uploaded file to temporary directory and return its path.
    
    Args:
        upload_file: FastAPI UploadFile object
        temp_dir: Temporary directory to save file
    
    Returns:
        Path to saved file
    """
    file_path = os.path.join(temp_dir, upload_file.filename)
    contents = await upload_file.read()
    with open(file_path, "wb") as f:
        f.write(contents)
    return file_path


@router.post("/generate/upload", response_model=PPTGenerationResponse, 
             tags=["Presentation Generation"],
             summary="Generate PPT from file uploads",
             description="Generate presentation by uploading startup info JSON, market research JSON, and optional logo image")
async def generate_ppt_from_files(
    startup_info: UploadFile = File(..., description="Startup information JSON file (required)"),
    market_research: UploadFile = File(..., description="Market research JSON file (required)"),
    logo: Optional[UploadFile] = File(None, description="Logo image file (optional, supports PNG/JPG)"),
    use_default_colors: bool = Form(True, description="Use default colors if no logo is provided"),
    color_palette: Optional[str] = Form(None, description="Optional color palette as JSON string (e.g., '[\"#FF0000\", \"#00FF00\"]')")
):
    """
    Generate a PowerPoint presentation from uploaded files.
    
    **Required Inputs:**
    - `startup_info`: JSON file containing startup information
    - `market_research`: JSON file containing market research data
    
    **Optional Inputs:**
    - `logo`: Image file (PNG/JPG) for the presentation
    - `use_default_colors`: Whether to use default color scheme (default: true)
    - `color_palette`: Custom color palette as JSON array
    
    **Returns:**
    - Generated PPTX file path and metadata
    """
    temp_dir = None
    try:
        # Create temporary directory for file processing
        temp_dir = tempfile.mkdtemp()
        logger.info(f"Using temporary directory: {temp_dir}")

        # Save and validate JSON files
        startup_path = await save_upload_file(startup_info, temp_dir)
        market_research_path = await save_upload_file(market_research, temp_dir)

        # Parse JSON files
        with open(startup_path, "r") as f:
            startup_data = json.load(f)
        
        with open(market_research_path, "r") as f:
            market_data = json.load(f)

        # Merge JSON files
        research_data = merge_json_files(startup_data, market_data)

        # Handle optional logo
        logo_path = None
        if logo:
            logo_path = await save_upload_file(logo, temp_dir)
            logger.info(f"Logo uploaded: {logo_path}")

        # Parse color palette if provided
        parsed_colors = None
        if color_palette:
            try:
                parsed_colors = json.loads(color_palette)
                if not isinstance(parsed_colors, list):
                    parsed_colors = None
            except json.JSONDecodeError:
                logger.warning("Invalid color palette JSON format, ignoring")
                parsed_colors = None

        # Create output filename
        timestamp = int(time.time())
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_filename = os.path.join(OUTPUT_DIR, f"presentation_{timestamp}.pptx")

        # Prepare state
        initial_state: PPTGenerationState = {
            "research_data": research_data,
            "logo_path": logo_path,
            "color_palette": parsed_colors,
            "use_default_colors": use_default_colors and not bool(logo_path),
            "draft": None,
            "critique": None,
            "iteration": 0,
            "ppt_path": None,
        }

        logger.info(f"Starting PPT generation with files: startup_info={startup_info.filename}, market_research={market_research.filename}")
        response = await run_ppt_generation(initial_state, output_filename)
        logger.info(f"PPT generation completed: {output_filename}")
        return response

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in uploaded files: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON format in uploaded files: {str(e)}"
        )
    except HTTPException:
        # Propagate HTTPException (e.g., 429 from run_ppt_generation) without wrapping
        raise
    except Exception as e:
        logger.error(f"Error in PPT generation from files: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    finally:
        # Cleanup temporary directory
        if temp_dir and os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info(f"Cleaned up temporary directory: {temp_dir}")


@router.post("/generate", response_model=PPTGenerationResponse,
             tags=["Presentation Generation"],
             summary="Generate PPT from merged JSON",
             description="Generate presentation from pre-merged JSON data (legacy endpoint)")
async def generate_ppt(input_data: PPTInput):
    """
    Single, main endpoint.

    Assumption (per project design):
    - The client has already loaded and merged the **two JSON input files**
      and passes them as `research_data` (string).
    - There are no CSV inputs.
    - Input files are guaranteed to exist and be valid on the client side.
    """
    timestamp = int(time.time())
    output_filename = os.path.join(OUTPUT_DIR, f"presentation_{timestamp}.pptx")

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
    return await run_ppt_generation(initial_state, output_filename)