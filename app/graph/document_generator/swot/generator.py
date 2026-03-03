import os
import json
import logging
from app.core.llm import get_llm
from .data_extractor import extract_swot_data
from app.graph.document_generator.prompts import swot_prompt_template
from app.graph.document_generator.config import (
    DEFAULT_LLM_PROVIDER, TEMPERATURE_GENERATOR, OUTPUT_DIR
)

logger = logging.getLogger("SWOTGenerator")

def generate_swot_document(idea_name: str, swot_context: dict, provider: str = DEFAULT_LLM_PROVIDER) -> dict:
    """
    Generates a full SWOT JSON document for a given idea name.
    
    Args:
        idea_name (str): The name of the business idea to generate for.
        swot_context (dict): The gathered SWOT context data.
        provider (str): LLM provider to use (default: gemini).
        
    Returns:
        dict: The generated JSON content as a dict, or an error message dict.
    """
    logger.info(f"Generating SWOT analysis for: {idea_name}")
    
    # 1. Ensure context exists
    if not swot_context or "error" in swot_context:
        error_msg = swot_context.get("error", "Invalid swot_context provided.")
        logger.error(error_msg)
        return {"error": error_msg}
        
    # Format context for the prompt
    def format_list(items):
        return "\n".join([f"- {item}" for item in items]) if items else "No specific data found."
        
    strengths_str = format_list(swot_context.get("strengths_context", []))
    weaknesses_str = format_list(swot_context.get("weaknesses_context", []))
    opportunities_str = format_list(swot_context.get("opportunities_context", []))
    threats_str = format_list(swot_context.get("threats_context", []))
    
    # 2. Extract TOWS
    tows_str = "\n\n".join(swot_context.get("tows_strategies", [])) if swot_context.get("tows_strategies") else "TOWS Strategies pending."
    verdict_str = swot_context.get("strategic_verdict", "Verdict pending.")
    
    # 3. Get LLM instance
    try:
        llm = get_llm(temperature=TEMPERATURE_GENERATOR, provider=provider)
    except Exception as e:
        logger.error(f"Failed to initialize LLM: {e}")
        return {"error": f"Error initializing LLM: {str(e)}"}
        
    # 3. Create chain and invoke
    try:
        chain = swot_prompt_template | llm
        
        logger.info("Invoking LLM for SWOT Generation...")
        response = chain.invoke({
            "idea_name": swot_context.get("idea_name", idea_name),
            "executive_summary": swot_context.get("executive_summary", "")[:1000] + "..." if len(swot_context.get("executive_summary", "")) > 1000 else swot_context.get("executive_summary", ""),
            "strengths_context": strengths_str,
            "weaknesses_context": weaknesses_str,
            "opportunities_context": opportunities_str,
            "threats_context": threats_str,
            "tows_strategies": tows_str,
            "strategic_verdict": verdict_str
        })
        
        json_content = response.content.replace("```json", "").replace("```", "").strip()
        swot_data = json.loads(json_content)
        
        # 4. Save to file
        output_dir = OUTPUT_DIR
        os.makedirs(output_dir, exist_ok=True)
        
        # Use clean name for filename
        clean_name = idea_name.replace(' ', '_').replace('"', '').replace("'", "")
        output_file = f"{output_dir}/{clean_name}_SWOT_Analysis.json"
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(swot_data, f, indent=4)
            
        logger.info(f"SWOT Analysis generated successfully: {output_file}")
        return swot_data
        
    except Exception as e:
        logger.error(f"Failed during SWOT LLM generation: {e}")
        return {"error": f"Error generating SWOT document: {str(e)}"}
