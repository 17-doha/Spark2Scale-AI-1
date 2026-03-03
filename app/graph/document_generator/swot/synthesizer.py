import os
import json
import logging
from app.core.llm import get_llm
from app.graph.document_generator.swot.data_extractor import extract_swot_data, _clean_filename
from app.graph.document_generator.prompts import TOWS_SYNTHESIS_PROMPT
from app.graph.document_generator.config import (
    DEFAULT_LLM_PROVIDER, TEMPERATURE_TOWS_SYNTHESIS, OUTPUT_DIR
)

logger = logging.getLogger("TOWSSynthesizer")

def synthesize_swot_matrix(idea_name: str) -> str:
    """
    Acts as the final 'Reducer' node. 
    It pulls all SWOT context, applies the TOWS framework, and generates
    a strategic matrix and final verdict using the LLM.
    """
    logger.info(f"\n[SYNTHESIZER] Generating TOWS Matrix and Strategic Verdict for: '{idea_name}'")
    
    # 1. Grab all the parsed context so far
    context = extract_swot_data(idea_name)
    if "error" in context:
        logger.error(f"[ERROR] Cannot synthesize TOWS: {context['error']}")
        return None
        
    def format_list(items):
        return "\n".join([f"- {item}" for item in items]) if items else "None identified."
        
    strengths_str = format_list(context.get("strengths_context", []))
    weaknesses_str = format_list(context.get("weaknesses_context", []))
    opportunities_str = format_list(context.get("opportunities_context", []))
    threats_str = format_list(context.get("threats_context", []))
    
    # Extract Pain Score and CAGR specifically if they exist in the strings
    pain_score = "Unknown"
    for s in context.get("strengths_context", []) + context.get("weaknesses_context", []):
         if "Pain Score" in s:
             pain_score = s
             break
             
    cagr = "Unknown"
    for o in context.get("opportunities_context", []) + context.get("threats_context", []):
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
        
        clean_name = _clean_filename(idea_name)
        output_path = f"{OUTPUT_DIR}/{clean_name}_tows_matrix.json"
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(tows_data, f, indent=4)
            
        logger.info(f"[SUCCESS] Saved TOWS Matrix to {output_path}")
        return output_path
        
    except json.JSONDecodeError as jde:
        logger.error(f"[ERROR] Failed to parse TOWS JSON from LLM: {content}")
        return None
    except Exception as e:
        logger.error(f"[ERROR] TOWS Synthesis Failed: {e}")
        return None
