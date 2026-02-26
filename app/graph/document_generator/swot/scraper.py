import os
import json
import logging
import pandas as pd
from app.graph.market_research_agent.helpers.research_utils import execute_serper_search
from typing import List, Dict

logger = logging.getLogger("CompetitorReviewScraper")

def _clean_filename(name: str) -> str:
    """Ensures consistent file naming across all nodes."""
    return name.replace(' ', '_').replace('"', '').replace("'", "")

def generate_review_queries(competitor_name: str) -> List[str]:
    """
    Generates targeted Serper API queries aiming for user pain points
    and negative reviews across Reddit, Trustpilot, and G2.
    """
    base_keywords = '"too expensive" OR "hard to use" OR "missing feature" OR "bad support" OR "alternative"'
    
    return [
        f"site:reddit.com {competitor_name} {base_keywords}",
        f"site:trustpilot.com {competitor_name} 1 star OR 2 star",
        f"site:g2.com {competitor_name} \"dislike\" OR \"cons\""
    ]

def scrape_competitor_reviews(idea_name: str) -> str:
    """
    Reads the associated competitors CSV, extracts top competitor names, 
    and searches for targeted user pain points to feed SWOT Weaknesses/Opportunities.
    
    Args:
        idea_name (str): The business idea name to locate the competitors CSV.
        
    Returns:
        str: Path to the saved competitor reviews JSON.
    """
    logger.info(f"\n[SCRAPER] Initiating Targeted Competitor Review Scrape for: '{idea_name}'")
    
    clean_name = _clean_filename(idea_name)
    competitors_file = f"data_output/{clean_name}_competitors.csv"
    
    if not os.path.exists(competitors_file):
        logger.warning(f"[WARNING] No competitors file found at {competitors_file}. Run Market Research first.")
        return None
        
    try:
        df = pd.read_csv(competitors_file)
        # Limit to top 3 competitors to save API calls and remain focused
        top_competitors = df['Name'].dropna().head(3).tolist()
    except Exception as e:
        logger.error(f"[ERROR] Failed to read competitors CSV: {e}")
        return None
        
    if not top_competitors:
         logger.warning("[WARNING] No valid competitor names found in CSV.")
         return None
         
    all_reviews_context = {}
    
    for competitor in top_competitors:
        # Ignore generic or placeholder names
        if competitor.lower() in ["data unavailable", "unknown"]:
            continue
            
        logger.info(f"   [SEARCH] Mining pain points for competitor: {competitor}")
        queries = generate_review_queries(competitor)
        
        # We limit the results from execute_serper_search
        raw_results = execute_serper_search(queries)
        
        if not raw_results:
            logger.info(f"   [INFO] No significant pain points found for {competitor}.")
            all_reviews_context[competitor] = ["No major negative signals found."]
            continue
            
        # Extract snippets that might contain the pain points
        snippets = []
        for res in raw_results:
            snippet = res.get("snippet", "")
            title = res.get("title", "")
            # Only store if it seems mildly relevant (basic heuristic: has some length)
            if len(snippet) > 20: 
                snippets.append(f"{title}: {snippet}")
                
        # Limit the stored context size per competitor
        all_reviews_context[competitor] = snippets[:5]
        
    # Save the output
    output_path = f"data_output/{clean_name}_competitor_reviews.json"
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_reviews_context, f, indent=4)
        logger.info(f"[SUCCESS] Saved competitor review context to {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"[ERROR] Failed to save competitor reviews JSON: {e}")
        return None
