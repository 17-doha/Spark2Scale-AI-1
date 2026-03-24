import os
import json
from app.core.llm import get_llm
from app.core.logger import get_logger
from app.graph.document_generator.swot.data_extractor import extract_swot_data, _clean_filename
from app.graph.document_generator.prompts import TOWS_SYNTHESIS_PROMPT
from app.graph.document_generator.config import (
    DEFAULT_LLM_PROVIDER, TEMPERATURE_TOWS_SYNTHESIS, OUTPUT_DIR
)

logger = get_logger("TOWSSynthesizer")

def synthesize_swot_matrix(idea_name: str, swot_context: dict) -> dict:
    """
    Acts as the final 'Reducer' node. 
    It pulls all SWOT context, applies the TOWS framework, and generates
    a strategic matrix and final verdict using the LLM.
    """
    logger.info(f"\n[SYNTHESIZER] Generating TOWS Matrix and Strategic Verdict for: '{idea_name}'")
    
    if not swot_context or "error" in swot_context:
        logger.error(f"[ERROR] Cannot synthesize TOWS, invalid swot_context.")
        return None
        
    def format_list(items):
        return "\n".join([f"- {item}" for item in items]) if items else "None identified."
        
    strengths_str = format_list(swot_context.get("strengths_context", []))
    weaknesses_str = format_list(swot_context.get("weaknesses_context", []))
    opportunities_str = format_list(swot_context.get("opportunities_context", []))
    threats_str = format_list(swot_context.get("threats_context", []))
    
    # Extract Pain Score and CAGR specifically if they exist in the strings
    pain_score = "Unknown"
    for s in swot_context.get("strengths_context", []) + swot_context.get("weaknesses_context", []):
         if "Pain Score" in s:
             pain_score = s
             break
             
    cagr = "Unknown"
    for o in swot_context.get("opportunities_context", []) + swot_context.get("threats_context", []):
         if "CAGR" in o or "Growth" in o:
             cagr = o
             break
             
    # 2. Analyze with LLM
    try:
        # Use a highly logical model
        llm = get_llm(temperature=TEMPERATURE_TOWS_SYNTHESIS, provider=DEFAULT_LLM_PROVIDER)
        
        prompt_text = TOWS_SYNTHESIS_PROMPT.format(
            idea_name=idea_name,
            pain_score=pain_score,
            cagr=cagr,
            strengths=strengths_str,
            weaknesses=weaknesses_str,
            opportunities=opportunities_str,
            threats=threats_str
        )
        
        logger.info("Invoking LLM for TOWS Synthesis...")
        response = llm.invoke(prompt_text)
        
        content = response.content.replace("```json", "").replace("```", "").strip()
        tows_data = json.loads(content)
        
        logger.info(f"[SUCCESS] TOWS Matrix parsed.")
        return tows_data
        
    except json.JSONDecodeError as jde:
        logger.error(f"[ERROR] Failed to parse TOWS JSON from LLM: {content}")
        return None
    except Exception as e:
        logger.error(f"[ERROR] TOWS Synthesis Failed: {e}")
        return None
