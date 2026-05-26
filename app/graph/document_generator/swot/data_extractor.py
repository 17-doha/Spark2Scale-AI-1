import os
import glob
import json
from app.core.logger import get_logger
from app.graph.document_generator.config import OUTPUT_DIR

logger = get_logger("SWOTDataExtractor")

def _clean_filename(name: str) -> str:
    """Ensures consistent file naming across all nodes."""
    return name.replace(' ', '_').replace('"', '').replace("'", "")

def extract_swot_data(
    idea_name: str,
    market_research: dict,
    weaknesses_data: dict = None,
    reviews_data: dict = None,
    gap_data: dict = None,
    barrier_data: dict = None,
    tows_data: dict = None,
    comment: str = None
) -> dict:
    """
    Extracts baseline data for SWOT quadrants from the given Market Research JSON
    and intermediate SWOT phase JSONs directly.
    Returns a dictionary of context structured for the SWOT LLM prompt.
    """
    if isinstance(weaknesses_data, list):
        weaknesses_data = {"weaknesses": weaknesses_data}
        
    if isinstance(gap_data, list):
        gap_data = {"opportunities": gap_data, "hard_strengths": []}
        
    if isinstance(barrier_data, list):
        barrier_data = {"regulatory_and_economic_threats": barrier_data}
        
    if isinstance(tows_data, list):
        tows_data = {"tows_matrix": {}, "strategic_verdict": ""}
    # --------------------------------------------------------------



    if not market_research:
        return {
            "error": f"No market research dict provided for idea: {idea_name}. Ensure Market Research is completed first."
        }
        
    try:
        if isinstance(market_research, list):
            market_research = market_research[0] if len(market_research) > 0 else {}
            
        raw = market_research.get("data") or market_research.get("items") or market_research
        data = raw[0] if isinstance(raw, list) and len(raw) > 0 else raw
        
        if isinstance(data, list):
            data = data[0] if len(data) > 0 else {}
            
        if not isinstance(data, dict):
            data = {}
        
        # Initialize SWOT context
        swot_context = {
            "idea_name": data.get("idea_name", idea_name),
            "executive_summary": data.get("executive_summary", ""),
            "strengths_context": [],
            "weaknesses_context": [],
            "opportunities_context": [],
            "threats_context": [],
            "tows_strategies": [],
            "strategic_verdict": "",
            "user_comment": comment or ""
        }
        
        # --- Strengths (Internal / Product Validations) ---
        validation = data.get("validation", {})
        if validation:
            pain_score = validation.get("pain_score", 0)
            verdict = validation.get("verdict", "")
            
            if pain_score >= 70 or verdict == "VALIDATED":
                swot_context["strengths_context"].append(
                    f"Strong validation with Pain Score {pain_score}/100 and verdict '{verdict}'."
                )
                
        # --- Analyzed Weaknesses → Weaknesses ---
        if weaknesses_data:
            if isinstance(weaknesses_data, list):
                weaknesses = weaknesses_data
            else:
                weaknesses = weaknesses_data.get("weaknesses", [])
            
            # Sort by severity so critical ones appear first
            weaknesses.sort(key=lambda w: w.get("severity", 0) if isinstance(w, dict) else 0, reverse=True)
            swot_context["weaknesses_context"] = weaknesses
        else:
            # Fallback for backward compatibility — warns that weaknesses are incomplete
            logger.warning(
                f"[FALLBACK] No analyzed_weaknesses provided for '{idea_name}'. "
                "Run scrape_weaknesses() + analyze_weaknesses() before SWOT generation."
            )
            if validation:
                pain_score = validation.get("pain_score", 0)
                if pain_score < 50:
                    swot_context["weaknesses_context"].append(
                        f"[METRIC][FALLBACK] Weak problem validation (Pain Score {pain_score}/100). "
                        "Run the weakness pipeline for full evidence-backed analysis."
                    )
                for w in validation.get("warnings", []):
                    swot_context["weaknesses_context"].append(f"[METRIC][FALLBACK] Validation Warning: {w}")
                
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
            comp_count = len([c for c in competitors if isinstance(c, dict) and c.get("Name") and c.get("Name") != "Data Unavailable"])
            if comp_count > 5:
                swot_context["threats_context"].append(f"High competition: at least {comp_count} direct competitors identified.")
            
            # Optionally summarize competitors features as a threat
            # or lack thereof as an opportunity context
            swot_context["competitors_count"] = comp_count

        # --- EXTRACT COMPETITOR REVIEWS (PHASE 2) ---
        if reviews_data:
            for comp, snippets in reviews_data.items():
                if snippets and "No major negative signals" not in snippets[0]:
                    opp_str = f"Competitor Weakness ({comp}): Users are complaining. Snippets: " + " | ".join(snippets[:3])
                    swot_context["opportunities_context"].append(f"Market Gap: {opp_str}")

        # --- EXTRACT COMPETITIVE GAPS (PHASE 3) ---
        if gap_data and isinstance(gap_data, dict): # FIX: Ensure it's a dict
            for strength in gap_data.get("hard_strengths", []):
                 swot_context["strengths_context"].append(strength)
                 
            for opp in gap_data.get("opportunities", []):
                 swot_context["opportunities_context"].append(opp)

        # --- EXTRACT REGULATORY BARRIERS (PHASE 4) ---
        if barrier_data and isinstance(barrier_data, dict): # FIX: Ensure it's a dict
            for threat in barrier_data.get("regulatory_and_economic_threats", []):
                 swot_context["threats_context"].append(threat)

        # --- EXTRACT TOWS MATRIX (PHASE 5) ---
        if tows_data and isinstance(tows_data, dict): # FIX: Ensure it's a dict
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

        return swot_context
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to extract SWOT data: {e}")
        return {
            "error": f"Error parsing market report: {str(e)}"
        }
