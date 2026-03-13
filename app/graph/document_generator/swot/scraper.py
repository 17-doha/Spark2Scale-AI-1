import os
import json
import logging
import pandas as pd
from app.graph.market_research_agent.helpers.research_utils import execute_serper_search
from typing import List, Dict
from app.core.llm import get_llm
from app.core.logger import get_logger
from app.graph.document_generator.prompts import WEAKNESS_ANALYSIS_PROMPT
from app.graph.document_generator.config import (
    DEFAULT_LLM_PROVIDER, TEMPERATURE_WEAKNESS_ANALYSIS, OUTPUT_DIR, TOP_COMPETITORS_LIMIT,
    SNIPPETS_PER_COMPETITOR_LIMIT, WEAKNESS_SNIPPETS_LIMIT, REVIEW_BASE_KEYWORDS,
    PAIN_SCORE_CRITICAL, PAIN_SCORE_MODERATE, SEARCH_VOLUME_LOW, SEARCH_VOLUME_MODERATE,
    CAC_VERY_HIGH, CAC_HIGH, LTV_CAC_POOR, LTV_CAC_WEAK, PAYBACK_PERIOD_DANGEROUS,
    PAYBACK_PERIOD_LONG, MARGIN_LOW, MARGIN_MODERATE, COMPETITOR_COUNT_SATURATED,
    COMPETITOR_COUNT_COMPETITIVE, MARKET_STRUCTURE_HIGH_RISK, MARKET_STRUCTURE_MODERATE_RISK_KEYWORD
)

logger = get_logger("CompetitorReviewScraper")
weakness_logger = get_logger("WeaknessAnalyzer")

def _clean_filename(name: str) -> str:
    """Ensures consistent file naming across all nodes."""
    return name.replace(' ', '_').replace('"', '').replace("'", "")

def generate_review_queries(competitor_name: str) -> List[str]:
    """
    Generates targeted Serper API queries aiming for user pain points
    and negative reviews across Reddit, Trustpilot, and G2.
    """
    base_keywords = REVIEW_BASE_KEYWORDS
    
    return [
        f"site:reddit.com {competitor_name} {base_keywords}",
        f"site:trustpilot.com {competitor_name} 1 star OR 2 star",
        f"site:g2.com {competitor_name} \"dislike\" OR \"cons\""
    ]

def scrape_competitor_reviews(idea_name: str, market_research: dict) -> dict:
    """
    Extracts top competitor names from the market research dict, 
    and searches for targeted user pain points to feed SWOT Weaknesses/Opportunities.
    
    Args:
        idea_name (str): The business idea name.
        market_research (dict): The output of the market research workflow.
        
    Returns:
        dict: A dictionary of competitor reviews/snippets.
    """
    logger.info(f"\n[SCRAPER] Initiating Targeted Competitor Review Scrape for: '{idea_name}'")
    
    if not market_research:
        logger.warning(f"[WARNING] No market research provided. Run Market Research first.")
        return None
        
    try:

        # 1. Defensively handle if market_research is accidentally a list
        if isinstance(market_research, list):
            market_research = market_research[0] if len(market_research) > 0 else {}
            
        data = market_research.get("data", market_research) if isinstance(market_research, dict) else market_research
        
        # 2. Defensively handle if data is accidentally a list
        if isinstance(data, list):
            data = data[0] if len(data) > 0 else {}
            
        # Ensure data is actually a dictionary before proceeding
        if not isinstance(data, dict):
            logger.warning("[WARNING] 'data' is not a dictionary. Cannot extract competitors.")
            return None

        competitors = data.get("competitors", [])
        
        # 3. Defensively handle if competitors is not a list
        if not isinstance(competitors, list):
            competitors = [competitors] if competitors else []

        # 4. Defensively check that 'c' is a dict before calling .get()
        top_competitors = [
            c.get("Name") for c in competitors 
            if isinstance(c, dict) and c.get("Name")
        ][:TOP_COMPETITORS_LIMIT]
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to extract competitors: {e}")
        return None
        
    if not top_competitors:
         logger.warning("[WARNING] No valid competitor names found in market research.")
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
        all_reviews_context[competitor] = snippets[:SNIPPETS_PER_COMPETITOR_LIMIT]
        
    # Save the output
    logger.info(f"[SUCCESS] Extracted competitor review context.")
    return all_reviews_context

def _generate_weakness_queries(idea_name: str, region: str = "Global") -> List[str]:
    return [
        f'"{idea_name}" startup problems OR challenges OR "why it fails"',
        f'site:reddit.com "{idea_name}" "doesn\'t work" OR "frustrated" OR "gave up" OR "waste of money"',
        f'"{idea_name}" product category "user complaints" OR "negative reviews" OR "missing feature"',
        f'"{idea_name}" market saturation OR "too many competitors" OR "commoditized" {region}',
        f'"{idea_name}" industry challenges founders "lessons learned" OR "common mistakes" {region}',
    ]


def scrape_weaknesses(idea_name: str, region: str = "Global") -> dict:
    weakness_logger.info(f"\n[WEAKNESS SCRAPER] Scraping weakness signals for: '{idea_name}' [{region}]")

    queries = _generate_weakness_queries(idea_name, region)
    raw_results = execute_serper_search(queries)

    if not raw_results:
        weakness_logger.warning("[WARNING] No search results returned for weakness scraping.")
        return None

    snippets = []
    seen = set()
    for res in raw_results:
        snippet = res.get("snippet", "").strip()
        title = res.get("title", "").strip()
        link = res.get("link", "")
        key = snippet[:80]
        if key in seen or len(snippet) < 25:
            continue
        seen.add(key)
        snippets.append({"title": title, "snippet": snippet, "source": link})

    snippets = snippets[:WEAKNESS_SNIPPETS_LIMIT]

    if not snippets:
        weakness_logger.warning("[WARNING] No usable snippets after deduplication.")
        return None

    weakness_logger.info(f"[SUCCESS] Weakness signals successfully gathered.")
    return {"idea_name": idea_name, "region": region, "signals": snippets}

def _extract_business_metrics(idea_name: str, market_research: dict) -> dict:
    """
    Pulls quantitative metrics from the market report that can signal weaknesses.
    Each metric is evaluated dynamically against thresholds — nothing is hardcoded.
    """
    if not market_research:
        return {}

    data = market_research.get("data", market_research) if isinstance(market_research, dict) else market_research

    metrics = {}

    # --- Validation metrics ---
    validation = data.get("validation", {})
    if validation:
        pain_score = validation.get("pain_score")
        if pain_score is not None:
            metrics["pain_score"] = {
                "value": pain_score,
                "threshold_label": (
                    "CRITICAL" if pain_score < PAIN_SCORE_CRITICAL else
                    "MODERATE" if pain_score < PAIN_SCORE_MODERATE else
                    "HEALTHY"
                )
            }
        search_volume = validation.get("monthly_search_volume")
        if search_volume is not None:
            metrics["monthly_search_volume"] = {
                "value": search_volume,
                "threshold_label": (
                    "LOW_DEMAND" if search_volume < SEARCH_VOLUME_LOW else
                    "MODERATE" if search_volume < SEARCH_VOLUME_MODERATE else
                    "HIGH"
                )
            }

    # --- Finance metrics ---
    finance = data.get("finance", {})
    if finance:
        fin_metrics = finance.get("metrics", {})

        cac = fin_metrics.get("estimated_cac")
        if cac is not None:
            try:
                cac_num = float(str(cac).replace("$", "").replace(",", "").split("-")[0].strip())
                metrics["estimated_cac"] = {
                    "value": cac,
                    "threshold_label": (
                        "VERY_HIGH" if cac_num > CAC_VERY_HIGH else
                        "HIGH" if cac_num > CAC_HIGH else
                        "ACCEPTABLE"
                    )
                }
            except Exception:
                metrics["estimated_cac"] = {"value": cac, "threshold_label": "UNKNOWN"}

        ltv = fin_metrics.get("estimated_ltv")
        cac_raw = fin_metrics.get("estimated_cac")
        if ltv and cac_raw:
            try:
                ltv_num = float(str(ltv).replace("$", "").replace(",", "").split("-")[0].strip())
                cac_num = float(str(cac_raw).replace("$", "").replace(",", "").split("-")[0].strip())
                ltv_cac_ratio = round(ltv_num / cac_num, 2) if cac_num > 0 else None
                if ltv_cac_ratio is not None:
                    metrics["ltv_cac_ratio"] = {
                        "value": ltv_cac_ratio,
                        "threshold_label": (
                            "POOR" if ltv_cac_ratio < LTV_CAC_POOR else
                            "WEAK" if ltv_cac_ratio < LTV_CAC_WEAK else
                            "HEALTHY"
                        )
                    }
            except Exception:
                pass

        payback_period = fin_metrics.get("payback_period_months")
        if payback_period is not None:
            try:
                pb_num = float(str(payback_period).split("-")[0].strip())
                metrics["payback_period_months"] = {
                    "value": payback_period,
                    "threshold_label": (
                        "DANGEROUSLY_LONG" if pb_num > PAYBACK_PERIOD_DANGEROUS else
                        "LONG" if pb_num > PAYBACK_PERIOD_LONG else
                        "ACCEPTABLE"
                    )
                }
            except Exception:
                pass

        margin = fin_metrics.get("estimated_gross_margin")
        if margin is not None:
            try:
                margin_num = float(str(margin).replace("%", "").replace(",", "").split("-")[0].strip())
                metrics["estimated_gross_margin"] = {
                    "value": margin,
                    "threshold_label": (
                        "LOW" if margin_num < MARGIN_LOW else
                        "MODERATE" if margin_num < MARGIN_MODERATE else
                        "HEALTHY"
                    )
                }
            except Exception:
                pass

    # --- Market sizing metrics ---
    sizing = data.get("market_sizing", {})
    if sizing:
        market_structure = sizing.get("market_structure", "")
        if market_structure:
            metrics["market_structure"] = {
                "value": market_structure,
                "threshold_label": (
                    "HIGH_RISK" if market_structure in MARKET_STRUCTURE_HIGH_RISK
                    else "MODERATE_RISK" if MARKET_STRUCTURE_MODERATE_RISK_KEYWORD in market_structure
                    else "LOW_RISK"
                )
            }

    # --- Competitor count ---
    competitors = data.get("competitors", [])
    comp_count = len([c for c in competitors if c.get("Name") and c.get("Name") != "Data Unavailable"])
    if comp_count:
        metrics["competitor_count"] = {
            "value": comp_count,
            "threshold_label": (
                "SATURATED" if comp_count > COMPETITOR_COUNT_SATURATED else
                "COMPETITIVE" if comp_count > COMPETITOR_COUNT_COMPETITIVE else
                "MANAGEABLE"
            )
        }

    return metrics


def analyze_weaknesses(idea_name: str, market_research: dict, idea_description: str = "A new product entering the market.", region: str = "Global") -> dict:
    """
    Combines scraped weakness signals with live business metrics and passes
    them to the LLM to produce structured, evidence-backed weaknesses for SWOT.

    The LLM classifies each weakness as either:
    - SCRAPE_BACKED: derived from real user/market complaints found on the web
    - METRIC_BACKED: derived from a quantitative business metric that crossed a threshold

    Args:
        idea_name (str): The business idea name.
        market_research (dict): Foundational market research data.
        idea_description (str): Short description of the idea for context.
        region (str): The target region for market analysis. Default is "Global".

    Returns:
        dict: The structure of analyzed weaknesses.
    """
    weakness_logger.info(f"\n[WEAKNESS ANALYZER] Analyzing weaknesses for: '{idea_name}'")

    clean_name = _clean_filename(idea_name)

    # 1. Scrape new live signals right now (instead of reading from disk)
    scraped_signals_data = scrape_weaknesses(idea_name, region)
    scraped_signals = scraped_signals_data.get("signals", []) if scraped_signals_data else []

    # 2. Extract dynamic business metrics from market report
    business_metrics = _extract_business_metrics(idea_name, market_research)

    if not scraped_signals and not business_metrics:
        weakness_logger.warning("[WARNING] No data available for weakness analysis. Skipping.")
        return None

    # 3. Invoke LLM for structured classification
    try:
        llm = get_llm(temperature=TEMPERATURE_WEAKNESS_ANALYSIS, provider=DEFAULT_LLM_PROVIDER)

        prompt_text = WEAKNESS_ANALYSIS_PROMPT.format(
            idea_name=idea_name,
            idea_description=idea_description,
            scraped_signals=json.dumps(scraped_signals, indent=2),
            business_metrics=json.dumps(business_metrics, indent=2)
        )

        weakness_logger.info("Invoking LLM for Weakness Classification...")
        response = llm.invoke(prompt_text)

        content = response.content.replace("```json", "").replace("```", "").strip()
        weakness_data = json.loads(content)

        weakness_logger.info(f"[SUCCESS] Analyzed weaknesses generated.")
        return weakness_data

    except json.JSONDecodeError:
        weakness_logger.error(f"[ERROR] Failed to parse weakness JSON from LLM: {content}")
        return None
    except Exception as e:
        weakness_logger.error(f"[ERROR] Weakness Analysis Failed: {e}")
        return None
