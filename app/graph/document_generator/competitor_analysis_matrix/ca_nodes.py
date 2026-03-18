import os
import re
import json
from typing import Dict, Any, List, Optional
from app.core.logger import get_logger
from app.graph.document_generator.state import DocumentGeneratorState
from app.core.rate_limiter import call_gemini
from app.graph.market_research_agent.helpers.research_utils import execute_serper_search
from app.graph.document_generator.prompts import classify_competitors_prompt
from app.graph.document_generator.config import OUTPUT_DIR

logger = get_logger("CompetitorAnalysisNodes")

# ══════════════════════════════════════════════════════════════════════════════
# NODE 1 — Extract competitor names from the market-research document
# ══════════════════════════════════════════════════════════════════════════════
def extract_competitors_from_market_research(state: DocumentGeneratorState) -> dict:
    logger.info("--- Node: extract_competitors_from_market_research ---")
    mr = state.get("market_research", {})
    
    comp_list = []
    if isinstance(mr, dict):
        if "competitors" in mr:
            comp_list = mr["competitors"]
        elif "data" in mr and isinstance(mr["data"], dict) and "competitors" in mr["data"]:
            comp_list = mr["data"]["competitors"]
            
    names = []
    for c in comp_list:
        if isinstance(c, dict) and "Name" in c:
            names.append(c["Name"])
        elif isinstance(c, str):
            names.append(c)
            
    profiles = []
    for name in names:
        profiles.append({
            "name": name,
            "company_website": None,
            "sw_profile": None,
            "linkedin_url": None,
            "physical_location": None,
            "competitor_type": None,
        })
        
    return {"competitor_names": names, "competitors": profiles}

# ══════════════════════════════════════════════════════════════════════════════
# Helper for Serper Links
# ══════════════════════════════════════════════════════════════════════════════
def _first_link(results: list, domain_hints: list = []) -> Optional[str]:
    """Pick the best matching link from Serper organic results."""
    for r in results:
        link = r.get("link", "")
        if domain_hints:
            for hint in domain_hints:
                if hint in link:
                    return link
        else:
            return link
    return None

# ══════════════════════════════════════════════════════════════════════════════
# NODE 2 — Enrich each competitor with web links via Serper
# ══════════════════════════════════════════════════════════════════════════════
def enrich_competitor_links(state: DocumentGeneratorState) -> dict:
    logger.info("--- Node: enrich_competitor_links ---")
    profiles = state.get("competitors", [])
    updated_profiles = []
    
    for profile in profiles:
        name = profile["name"]
        
        q_site = f"{name} official website"
        q_g2 = f"{name} site:g2.com OR site:capterra.com OR site:producthunt.com"
        q_li = f"{name} company LinkedIn"
        q_hq = f"{name} company headquarters location"
        
        queries = [q_site, q_g2, q_li, q_hq]
        raw_results = execute_serper_search(queries)
        
        exclude = ("linkedin.", "g2.com", "capterra.", "producthunt.", "crunchbase.")
        for r in raw_results:
            link = r.get("link", "")
            if not any(ex in r.get("link", "").lower() for ex in exclude):
                profile["company_website"] = profile.get("company_website") or link
        
        link_sw = _first_link(raw_results, domain_hints=["g2.com", "capterra.com", "producthunt.com"])
        if link_sw:
            profile["sw_profile"] = link_sw
            
        link_li = _first_link(raw_results, domain_hints=["linkedin.com/company"])
        if link_li:
            profile["linkedin_url"] = link_li
            
        location_text = None
        for r in raw_results:
            snippet = r.get("snippet", "")
            match = re.search(
                r"(?:headquartered|based|located|hq)\s+in\s+([A-Z][^,.]+(?:,\s*[A-Z][^,.]+)?)",
                snippet,
                re.IGNORECASE,
            )
            if match:
                location_text = match.group(1).strip()
                break
        profile["physical_location"] = location_text

        updated_profiles.append(profile)

    return {"competitors": updated_profiles}

# ══════════════════════════════════════════════════════════════════════════════
# NODE 3 — Classify each competitor as direct or indirect (Gemini LLM)
# ══════════════════════════════════════════════════════════════════════════════
def classify_competitor_type(state: DocumentGeneratorState) -> dict:
    logger.info("--- Node: classify_competitor_type ---")
    profiles = state.get("competitors", [])
    if not profiles:
        return {"competitors": []}
        
    comps_listing = "\n".join([f"- {p['name']} (Website: {p.get('company_website') or 'unknown'})" for p in profiles])
    idea_desc = state.get("idea_description") or state.get("idea_name", "start-up")

    prompt = classify_competitors_prompt(idea_desc, comps_listing)
    
    try:
        response = call_gemini(prompt)
        raw = response.text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"```$", "", raw).strip()
        
        classification_dict = json.loads(raw)
        
        for profile in profiles:
            c_name = profile["name"]
            comp_type = classification_dict.get(c_name, classification_dict.get(c_name.lower(), "indirect"))
            if isinstance(comp_type, str):
                comp_type = comp_type.lower()
            if comp_type not in ("direct", "indirect"):
                comp_type = "indirect"
                
            profile["competitor_type"] = comp_type

    except Exception as exc:
        logger.warning(f"[classify_competitor_type] Warning: {exc}")
        for profile in profiles:
            profile["competitor_type"] = "indirect"

    return {"competitors": profiles}

# ══════════════════════════════════════════════════════════════════════════════
# NODE 4 — Aggregate into the final matrix state (ready for doc generation)
# ══════════════════════════════════════════════════════════════════════════════
def build_competitor_matrix(state: DocumentGeneratorState) -> dict:
    logger.info("--- Node: build_competitor_matrix ---")
    profiles = state.get("competitors", [])
    
    sorted_profiles = sorted(
        profiles,
        key=lambda p: (0 if p.get("competitor_type") == "direct" else 1, p["name"]),
    )
    
    incomplete = [
        p["name"] for p in sorted_profiles
        if not p.get("company_website") or not p.get("competitor_type")
    ]
    if incomplete:
        logger.info(f"[build_competitor_matrix] Incomplete profiles: {incomplete}")
        
    # Generate Markdown Table
    md = "## Competitor Analysis Matrix\n\n"
    md += "| Competitor | Type | HQ Location | Website | Review Profile | LinkedIn |\n"
    md += "|---|---|---|---|---|---|\n"
    
    for p in sorted_profiles:
        name = p.get("name", "N/A")
        ctype = str(p.get("competitor_type", "N/A")).capitalize()
        hq = p.get("physical_location") or "Unknown"
        
        web = p.get("company_website")
        web_link = f"[Website]({web})" if web else "N/A"
        
        sw = p.get("sw_profile")
        sw_link = f"[Profile]({sw})" if sw else "N/A"
        
        li = p.get("linkedin_url")
        li_link = f"[LinkedIn]({li})" if li else "N/A"
        
        md += f"| {name} | **{ctype}** | {hq} | {web_link} | {sw_link} | {li_link} |\n"
        
    # Save the file
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        filename = state.get("idea_name", "startup").replace(" ", "_").replace("/", "_").lower()
        filepath = os.path.join(OUTPUT_DIR, f"{filename}_competitor_analysis.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md)
        logger.info(f"[build_competitor_matrix] Saved Competitor Matrix to: {filepath}")
    except Exception as e:
        logger.error(f"[build_competitor_matrix] Could not save markdown file: {e}")
        
    return {
        "competitors": sorted_profiles,
        "competitor_analysis_document": {"markdown": md, "status": "completed"}
    }
