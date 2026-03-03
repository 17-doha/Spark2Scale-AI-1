import os
import glob
import json
import logging

logger = logging.getLogger("SWOTDataExtractor")

def _clean_filename(name: str) -> str:
    """Ensures consistent file naming across all nodes."""
    return name.replace(' ', '_').replace('"', '').replace("'", "")

def find_market_report(idea_name: str) -> str:
    """
    Robustly finds the market report JSON file, accounting for potential 
    shortening or modification of the idea name due to length or formatting limits.
    """
    if not idea_name:
        return None
        
    clean_name = idea_name.replace(' ', '_').replace('"', '').replace("'", "")
    
    # 1. Try exact match
    exact_path = f"data_output/{clean_name}_Market_Report.json"
    if os.path.exists(exact_path):
        return exact_path
        
    # 2. Try prefix matching if the name was truncated
    # Use first 20-30 chars of the clean name (or whatever length is available)
    prefix_length = min(len(clean_name), 25)
    prefix = clean_name[:prefix_length]
    
    # Search for files starting with the prefix and ending with _Market_Report.json
    pattern = f"data_output/{prefix}*_Market_Report.json"
    matches = glob.glob(pattern)
    
    if matches:
        # If multiple matches, sort by modification time (newest first)
        matches.sort(key=os.path.getmtime, reverse=True)
        return matches[0]
        
    logger.warning(f"[WARNING] Could not find Market Report JSON for idea: {idea_name}")
    return None

def extract_swot_data(idea_name: str) -> dict:
    """
    Extracts baseline data for SWOT quadrants from the generated Market Research JSON.
    Returns a dictionary of context structured for the SWOT LLM prompt.
    """
    report_path = find_market_report(idea_name)
    if not report_path:
        return {
            "error": f"No market report found for idea: {idea_name}. Ensure Market Research is completed first."
        }
        
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        # Initialize SWOT context
        swot_context = {
            "idea_name": data.get("idea_name", idea_name),
            "executive_summary": data.get("executive_summary", ""),
            "strengths_context": [],
            "weaknesses_context": [],
            "opportunities_context": [],
            "threats_context": [],
            "tows_strategies": [],
            "strategic_verdict": ""
        }
        
        # --- Strengths & Weaknesses (Internal / Product Validations) ---
        validation = data.get("validation", {})
        if validation:
            pain_score = validation.get("pain_score", 0)
            verdict = validation.get("verdict", "")
            
            if pain_score >= 70 or verdict == "VALIDATED":
                swot_context["strengths_context"].append(
                    f"Strong validation with Pain Score {pain_score}/100 and verdict '{verdict}'."
                )
            elif pain_score < 50:
                swot_context["weaknesses_context"].append(
                    f"Weak problem validation (Pain Score {pain_score}/100). The core problem may not be significant enough."
                )
                
            warnings = validation.get("warnings", [])
            for w in warnings:
                swot_context["weaknesses_context"].append(f"Validation Warning: {w}")
                
        # Look at Finance for Strengths/Weaknesses
        finance = data.get("finance", {})
        if finance:
            margin = finance.get("metrics", {}).get("estimated_gross_margin", "")
            if margin:
                # If margin is something like "70% - 85%", consider it a strength
                swot_context["strengths_context"].append(f"Estimated Margins: {margin}")

        # --- Opportunities & Threats (External / Market) ---
        # Look at Trends
        trends = data.get("trends", [])
        for t in trends:
            metric = t.get("metric", "")
            val = t.get("value", "")
            source = t.get("source", "")
            if "growth" in str(metric).lower() or "cagr" in str(source).lower():
                # Convert to float if possible
                try:
                    num_val = float(str(val).replace('%', ''))
                    if num_val > 5.0:
                        swot_context["opportunities_context"].append(f"High Market Growth (CAGR): {val}% from {source}")
                    else:
                        swot_context["threats_context"].append(f"Slow Market Growth: {val}% from {source}")
                except:
                    swot_context["opportunities_context"].append(f"Market Growth Trend: {val}% ({source})")

        # Look at Market Sizing
        sizing = data.get("market_sizing", {})
        if sizing:
            market_structure = sizing.get("market_structure", "")
            if market_structure == "Highly Fragmented/Red Ocean":
                swot_context["threats_context"].append("Highly competitive 'Red Ocean' market structure.")
            elif market_structure == "Oligopoly/Monopoly":
                swot_context["threats_context"].append("Market is dominated by a few large players (Oligopoly/Monopoly).")
            elif market_structure == "Emerging/Blue Ocean":
                swot_context["opportunities_context"].append("Emerging 'Blue Ocean' market with less entrenched competition.")
                
            tam = sizing.get("tam_value", "")
            if tam:
                swot_context["opportunities_context"].append(f"Large Total Addressable Market (TAM): {tam}")

        # Look at Competitors
        competitors = data.get("competitors", [])
        if competitors:
            comp_count = len([c for c in competitors if c.get("Name") and c.get("Name") != "Data Unavailable"])
            if comp_count > 5:
                swot_context["threats_context"].append(f"High competition: at least {comp_count} direct competitors identified.")
            
            # Optionally summarize competitors features as a threat
            # or lack thereof as an opportunity context
            swot_context["competitors_count"] = comp_count

        # --- EXTRACT COMPETITOR REVIEWS (PHASE 2) ---
        clean_name = _clean_filename(idea_name)
        reviews_path = f"data_output/{clean_name}_competitor_reviews.json"
        
        if os.path.exists(reviews_path):
            try:
                with open(reviews_path, "r", encoding="utf-8") as f:
                    reviews_data = json.load(f)
                    
                for comp, snippets in reviews_data.items():
                    if snippets and "No major negative signals" not in snippets[0]:
                        opp_str = f"Competitor Weakness ({comp}): Users are complaining. Snippets: " + " | ".join(snippets[:3])
                        swot_context["opportunities_context"].append(f"Market Gap: {opp_str}")
            except Exception as e:
                logger.error(f"[ERROR] Failed to read competitor reviews: {e}")

        # --- EXTRACT COMPETITIVE GAPS (PHASE 3) ---
        gap_path = f"data_output/{clean_name}_competitive_gap.json"
        if os.path.exists(gap_path):
            try:
                with open(gap_path, "r", encoding="utf-8") as f:
                    gap_data = json.load(f)
                    
                for strength in gap_data.get("hard_strengths", []):
                     swot_context["strengths_context"].append(strength)
                     
                for opp in gap_data.get("opportunities", []):
                     swot_context["opportunities_context"].append(opp)
            except Exception as e:
                logger.error(f"[ERROR] Failed to read competitive gap data: {e}")

        # --- EXTRACT REGULATORY BARRIERS (PHASE 4) ---
        barriers_path = f"data_output/{clean_name}_barriers.json"
        if os.path.exists(barriers_path):
            try:
                with open(barriers_path, "r", encoding="utf-8") as f:
                    barrier_data = json.load(f)
                    
                for threat in barrier_data.get("regulatory_and_economic_threats", []):
                     swot_context["threats_context"].append(threat)
            except Exception as e:
                logger.error(f"[ERROR] Failed to read regulatory barriers data: {e}")

        # --- EXTRACT TOWS MATRIX (PHASE 5) ---
        tows_path = f"data_output/{clean_name}_tows_matrix.json"
        if os.path.exists(tows_path):
            try:
                with open(tows_path, "r", encoding="utf-8") as f:
                    tows_data = json.load(f)
                    
                matrix = tows_data.get("tows_matrix", {})
                
                if matrix.get("SO_Strategies"):
                    swot_context["tows_strategies"].append("**SO Strategies (Maxi-Maxi):**\n" + "\n".join([f"- {s}" for s in matrix["SO_Strategies"]]))
                if matrix.get("ST_Strategies"):
                    swot_context["tows_strategies"].append("**ST Strategies (Maxi-Mini):**\n" + "\n".join([f"- {s}" for s in matrix["ST_Strategies"]]))
                if matrix.get("WO_Strategies"):
                    swot_context["tows_strategies"].append("**WO Strategies (Mini-Maxi):**\n" + "\n".join([f"- {s}" for s in matrix["WO_Strategies"]]))
                if matrix.get("WT_Strategies"):
                    swot_context["tows_strategies"].append("**WT Strategies (Mini-Mini):**\n" + "\n".join([f"- {s}" for s in matrix["WT_Strategies"]]))
                    
                swot_context["strategic_verdict"] = tows_data.get("strategic_verdict", "No unified verdict available.")
            except Exception as e:
                logger.error(f"[ERROR] Failed to read TOWS Matrix data: {e}")

        return swot_context
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to extract SWOT data: {e}")
        return {
            "error": f"Error parsing market report: {str(e)}"
        }
