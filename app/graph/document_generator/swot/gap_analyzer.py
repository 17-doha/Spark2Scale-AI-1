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

def analyze_competitive_gap(idea_name: str, idea_description: str = "A new product entering the market.") -> str:
    """
    Reads the scraped competitor reviews, passes them to an LLM to determine
    Hard Strengths vs Opportunities when compared to the new business idea,
    and saves the structured output.
    """
    logger.info(f"\n[ANALYZER] Running Competitive Gap Analysis for: '{idea_name}'")
    
    clean_name = _clean_filename(idea_name)
    reviews_path = f"{OUTPUT_DIR}/{clean_name}_competitor_reviews.json"
    
    if not os.path.exists(reviews_path):
        logger.warning(f"[WARNING] No reviews file found at {reviews_path}. Cannot perform Gap Analysis.")
        return None
        
    try:
        with open(reviews_path, "r", encoding="utf-8") as f:
            reviews_data = json.load(f)
            
        # If there are no meaningful reviews, skip
        has_data = any(v and "No major negative signals" not in v[0] for v in reviews_data.values())
        if not has_data:
            logger.info("[INFO] No negative signals found in reviews to analyze.")
            return None
            
    except Exception as e:
        logger.error(f"[ERROR] Failed to read competitor reviews: {e}")
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
        
        output_path = f"{OUTPUT_DIR}/{clean_name}_competitive_gap.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(gap_data, f, indent=4)
            
        logger.info(f"[SUCCESS] Saved Competitive Gap Analysis to {output_path}")
        return output_path
        
    except json.JSONDecodeError as jde:
        logger.error(f"[ERROR] Failed to parse Gap Analysis JSON output from LLM: {content}")
        return None
    except Exception as e:
        logger.error(f"[ERROR] Gap Analysis Failed: {e}")
        return None
