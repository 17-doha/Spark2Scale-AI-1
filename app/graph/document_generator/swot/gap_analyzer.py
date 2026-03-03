import os
import json
import logging
from app.core.llm import get_llm
from app.graph.document_generator.swot.data_extractor import _clean_filename
from app.graph.document_generator.prompts import GAP_ANALYZER_PROMPT
from app.graph.document_generator.config import (
    DEFAULT_LLM_PROVIDER, TEMPERATURE_GAP_ANALYZER, OUTPUT_DIR
)

logger = logging.getLogger("CompetitiveGapAnalyzer")

def analyze_competitive_gap(idea_name: str, reviews_data: dict, idea_description: str = "A new product entering the market.") -> dict:
    """
    Reads the scraped competitor reviews dict, passes them to an LLM to determine
    Hard Strengths vs Opportunities when compared to the new business idea,
    and returns the structured output.
    """
    logger.info(f"\n[ANALYZER] Running Competitive Gap Analysis for: '{idea_name}'")
    
    if not reviews_data:
        logger.warning(f"[WARNING] No reviews data provided. Cannot perform Gap Analysis.")
        return None
        
    # If there are no meaningful reviews, skip
    has_data = any(v and "No major negative signals" not in v[0] for v in reviews_data.values())
    if not has_data:
        logger.info("[INFO] No negative signals found in reviews to analyze.")
        return None

    try:
        # We explicitly use a fast/reliable LLM for this logic step (Groq/Gemini contextually)
        llm = get_llm(temperature=TEMPERATURE_GAP_ANALYZER, provider=DEFAULT_LLM_PROVIDER) # Lower temp for logical mapping
        
        prompt_text = GAP_ANALYZER_PROMPT.format(
            idea_name=idea_name,
            idea_description=idea_description,
            reviews_json=json.dumps(reviews_data, indent=2)
        )
        
        logger.info("Invoking LLM for Gap Analysis...")
        # Direct generation call
        response = llm.invoke(prompt_text)
        
        # Clean the response in case the LLM returned markdown blocks despite the prompt
        content = response.content.replace("```json", "").replace("```", "").strip()
        
        gap_data = json.loads(content)
        
        logger.info(f"[SUCCESS] Gap Analysis finished.")
        return gap_data
        
    except json.JSONDecodeError as jde:
        logger.error(f"[ERROR] Failed to parse Gap Analysis JSON output from LLM: {content}")
        return None
    except Exception as e:
        logger.error(f"[ERROR] Gap Analysis Failed: {e}")
        return None
