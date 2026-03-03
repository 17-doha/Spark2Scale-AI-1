import os
import json
import logging
import pandas as pd
from app.graph.market_research_agent.helpers.research_utils import execute_serper_search
from typing import List, Dict
from app.core.llm import get_llm
from app.graph.document_generator.swot.data_extractor import find_market_report
from app.graph.document_generator.prompts import WEAKNESS_ANALYSIS_PROMPT

logger = logging.getLogger("CompetitorReviewScraper")
weakness_logger = logging.getLogger("WeaknessAnalyzer")

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

def _generate_weakness_queries(idea_name: str, region: str = "Global") -> List[str]:
    return [
        f'"{idea_name}" startup problems OR challenges OR "why it fails"',
        f'site:reddit.com "{idea_name}" "doesn\'t work" OR "frustrated" OR "gave up" OR "waste of money"',
        f'"{idea_name}" product category "user complaints" OR "negative reviews" OR "missing feature"',
        f'"{idea_name}" market saturation OR "too many competitors" OR "commoditized" {region}',
        f'"{idea_name}" industry challenges founders "lessons learned" OR "common mistakes" {region}',
    ]


def scrape_weaknesses(idea_name: str, region: str = "Global") -> str:
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

    snippets = snippets[:20]

    if not snippets:
        weakness_logger.warning("[WARNING] No usable snippets after deduplication.")
        return None

    clean_name = _clean_filename(idea_name)
    output_path = f"data_output/{clean_name}_weakness_signals.json"
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"idea_name": idea_name, "region": region, "signals": snippets}, f, indent=4)
        weakness_logger.info(f"[SUCCESS] Saved weakness signals to {output_path}")
        return output_path
    except Exception as e:
        weakness_logger.error(f"[ERROR] Failed to save weakness signals: {e}")
        return None

def _extract_business_metrics(idea_name: str) -> dict:
    """
    Pulls quantitative metrics from the market report that can signal weaknesses.
    Each metric is evaluated dynamically against thresholds — nothing is hardcoded.
    """
    report_path = find_market_report(idea_name)
    if not report_path:
        return {}

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        weakness_logger.warning(f"[WARNING] Could not read market report for metrics: {e}")
        return {}

    metrics = {}

    # --- Validation metrics ---
    validation = data.get("validation", {})
    if validation:
        pain_score = validation.get("pain_score")
        if pain_score is not None:
            metrics["pain_score"] = {
                "value": pain_score,
                "threshold_label": (
                    "CRITICAL" if pain_score < 40 else
                    "MODERATE" if pain_score < 65 else
                    "HEALTHY"
                )
            }
        search_volume = validation.get("monthly_search_volume")
        if search_volume is not None:
            metrics["monthly_search_volume"] = {
                "value": search_volume,
                "threshold_label": (
                    "LOW_DEMAND" if search_volume < 1000 else
                    "MODERATE" if search_volume < 10000 else
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
                        "VERY_HIGH" if cac_num > 500 else
                        "HIGH" if cac_num > 150 else
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
                            "POOR" if ltv_cac_ratio < 1.5 else
                            "WEAK" if ltv_cac_ratio < 3.0 else
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
                        "DANGEROUSLY_LONG" if pb_num > 24 else
                        "LONG" if pb_num > 12 else
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
                        "LOW" if margin_num < 30 else
                        "MODERATE" if margin_num < 60 else
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
                    "HIGH_RISK" if market_structure in ["Oligopoly/Monopoly", "Highly Fragmented/Red Ocean"]
                    else "MODERATE_RISK" if "Competitive" in market_structure
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
                "SATURATED" if comp_count > 10 else
                "COMPETITIVE" if comp_count > 5 else
                "MANAGEABLE"
            )
        }

    return metrics


def analyze_weaknesses(idea_name: str, idea_description: str = "A new product entering the market.", region: str = "Global") -> str:
    """
    Combines scraped weakness signals with live business metrics and passes
    them to the LLM to produce structured, evidence-backed weaknesses for SWOT.

    The LLM classifies each weakness as either:
    - SCRAPE_BACKED: derived from real user/market complaints found on the web
    - METRIC_BACKED: derived from a quantitative business metric that crossed a threshold

    Args:
        idea_name (str): The business idea name.
        idea_description (str): Short description of the idea for context.
        region (str): The target region for market analysis. Default is "Global".

    Returns:
        str: Path to saved analyzed_weaknesses JSON, or None on failure.
    """
    weakness_logger.info(f"\n[WEAKNESS ANALYZER] Analyzing weaknesses for: '{idea_name}'")

    clean_name = _clean_filename(idea_name)

    # Auto-run scraper if signals file doesn't exist yet
    signals_path = f"data_output/{clean_name}_weakness_signals.json"
    if not os.path.exists(signals_path):
        weakness_logger.info("[INFO] No weakness signals found — running scraper now.")
        scrape_weaknesses(idea_name, region)

    scraped_signals = []
    if os.path.exists(signals_path):
        try:
            with open(signals_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            scraped_signals = raw.get("signals", [])
        except Exception as e:
            weakness_logger.warning(f"[WARNING] Could not load weakness signals: {e}")
    else:
        weakness_logger.warning(f"[WARNING] No weakness signals file at {signals_path}. Proceeding with metrics only.")

    # 2. Extract dynamic business metrics from market report
    business_metrics = _extract_business_metrics(idea_name)

    if not scraped_signals and not business_metrics:
        weakness_logger.warning("[WARNING] No data available for weakness analysis. Skipping.")
        return None

    # 3. Invoke LLM for structured classification
    try:
        llm = get_llm(temperature=0.2, provider="gemini")

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

        output_path = f"data_output/{clean_name}_analyzed_weaknesses.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(weakness_data, f, indent=4)

        weakness_logger.info(f"[SUCCESS] Saved analyzed weaknesses to {output_path}")
        return output_path

    except json.JSONDecodeError:
        weakness_logger.error(f"[ERROR] Failed to parse weakness JSON from LLM: {content}")
        return None
    except Exception as e:
        weakness_logger.error(f"[ERROR] Weakness Analysis Failed: {e}")
        return None
