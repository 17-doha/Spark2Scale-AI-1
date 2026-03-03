import os
import json
import logging
from app.graph.market_research_agent.helpers.research_utils import execute_serper_search
from app.graph.document_generator.swot.data_extractor import _clean_filename
from app.core.llm import get_llm
from app.graph.document_generator.prompts import BARRIER_EXTRACTION_PROMPT
from app.graph.document_generator.config import (
    DEFAULT_LLM_PROVIDER, TEMPERATURE_BARRIER_EXTRACTION, OUTPUT_DIR, BARRIER_SNIPPETS_LIMIT
)

logger = logging.getLogger("RegulatoryBarrierNode")

def scrape_regulatory_barriers(idea_name: str, region: str = "Global") -> dict:
    """
    Scrapes the web for legal, compliance, and economic barriers in the given region.
    Summarizes them using an LLM to feed into the SWOT Threats quadrant.
    Returns a dict containing the barrier data.
    """
    logger.info(f"\n[PEST] Scraping Regulatory & Economic Barriers for: '{idea_name}' in Region: '{region}'")
    
    # 1. Generate search queries
    queries = [
        f"{idea_name} regulatory compliance laws {region}",
        f"{idea_name} legal challenges {region}",
        f"{idea_name} startup economic barriers {region}"
    ]
    
    # 2. Execute Serper Search
    raw_results = execute_serper_search(queries)
    if not raw_results:
        logger.warning(f"[WARNING] No search results found for regulatory barriers.")
        return None
        
    snippets = []
    for res in raw_results:
        snippet = res.get("snippet", "")
        title = res.get("title", "")
        if len(snippet) > 20: 
            snippets.append(f"{title}: {snippet}")
            
    # Limit snippets
    search_context = "\n".join(snippets[:BARRIER_SNIPPETS_LIMIT])
    
    if not search_context:
        logger.warning("[WARNING] No meaningful content extracted from snippets.")
        return None
    
    # 3. Analyze with LLM
    try:
        llm = get_llm(temperature=TEMPERATURE_BARRIER_EXTRACTION, provider=DEFAULT_LLM_PROVIDER)
        
        prompt_text = BARRIER_EXTRACTION_PROMPT.format(
            idea_name=idea_name,
            region=region,
            search_snippets=search_context
        )
        
        logger.info("Invoking LLM for PEST Barrier Analysis...")
        response = llm.invoke(prompt_text)
        
        content = response.content.replace("```json", "").replace("```", "").strip()
        barrier_data = json.loads(content)
        
        logger.info(f"[SUCCESS] PEST Barriers parsed.")
        return barrier_data
        
    except json.JSONDecodeError as jde:
        logger.error(f"[ERROR] Failed to parse Barrier JSON from LLM: {content}")
        return None
    except Exception as e:
        logger.error(f"[ERROR] PEST Barrier Analysis Failed: {e}")
        return None
