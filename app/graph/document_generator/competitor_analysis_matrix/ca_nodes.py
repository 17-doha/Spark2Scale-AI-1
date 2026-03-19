import os
import re
import json
from typing import Dict, Any, List, Optional
from app.core.logger import get_logger
from app.graph.document_generator.state import DocumentGeneratorState
from app.core.rate_limiter import call_gemini
from app.graph.market_research_agent.helpers.research_utils import execute_serper_search
from app.graph.document_generator.prompts import (
    classify_competitors_prompt, 
    enrich_market_intelligence_prompt,
    enrich_product_reality_prompt
)
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
            
    # Limit the competitors to 5 max
    names = names[:5]
            
    profiles = []
    for name in names:
        profiles.append({
            "name": name,
            "company_website": None,
            "sw_profile": None,
            "linkedin_url": None,
            "physical_location": None,
            "competitor_type": None,
            "target_audience": None,
            "value_proposition": None,
            "pricing_model": None,
            "core_features": None,
            "strengths": None,
            "weaknesses": None,
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
        
        # ── Call 1: official website
        q_site = f"{name} official website"
        # ── Call 2: software review profiles (separate to prevent dilution)
        q_g2 = f"{name} site:g2.com"
        q_capterra = f"{name} site:capterra.com"
        q_ph = f"{name} site:producthunt.com"
        # ── Call 3: LinkedIn company page
        q_li = f"{name} company LinkedIn"
        # ── Call 4: HQ location (triggers knowledge panel)
        q_hq = f"{name} company headquarters location"
        
        queries = [q_site, q_g2, q_capterra, q_ph, q_li, q_hq]
        raw_results = execute_serper_search(queries)
        
        exclude_from_site = ("linkedin.", "g2.com", "capterra.", "producthunt.", "crunchbase.")
        
        for r in raw_results:
            link = r.get("link", "")
            snippet = r.get("snippet", "")
            
            # Official website
            if not profile.get("company_website") and not any(ex in link.lower() for ex in exclude_from_site):
                profile["company_website"] = link
                
            # LinkedIn
            if not profile.get("linkedin_url") and "linkedin.com/company" in link.lower():
                profile["linkedin_url"] = link
                
            # Review Profile (Grab first one found from the review queries)
            if not profile.get("sw_profile") and any(domain in link.lower() for domain in ("g2.com", "capterra.com", "producthunt.com")):
                profile["sw_profile"] = link
                
            # Physical Location
            if not profile.get("physical_location") and snippet:
                match = re.search(
                    r"(?:headquartered|based|located|hq)\s+in\s+([A-Z][^,.]{2,40}(?:,\s*[A-Z][^,.]{2,30})?)",
                    snippet,
                    re.IGNORECASE,
                )
                if match:
                    profile["physical_location"] = match.group(1).strip()

        updated_profiles.append(profile)

    return {"competitors": updated_profiles}

# ══════════════════════════════════════════════════════════════════════════════
# NODE 2b — Enrich market intelligence: audience, value prop, pricing
# ══════════════════════════════════════════════════════════════════════════════
def enrich_market_intelligence(state: DocumentGeneratorState) -> dict:
    logger.info("--- Node: enrich_market_intelligence ---")
    profiles = state.get("competitors", [])
    if not profiles:
        return {"competitors": []}

    batched_evidence = []
    
    for profile in profiles:
        name = profile["name"]
        site = profile.get("company_website") or ""
        sw   = profile.get("sw_profile") or ""

        evidence_blocks = []

        q_broad = f"{name} pricing plans who is it for target customers review"
        raw_results = execute_serper_search([q_broad])
        
        # Keep top 8 roughly
        for r in raw_results[:8]:
            snippet = r.get("snippet", "")
            title = r.get("title", "")
            link = r.get("link", "")
            if snippet:
                evidence_blocks.append(f"[{title}] ({link})\n{snippet}")
                
        evidence_text = "\n\n".join(evidence_blocks) if evidence_blocks else "No evidence found."
        batched_evidence.append(f"### Competitor: {name}\nWebsite: {site}\n{evidence_text}")
        
    batched_evidence_text = "\n\n---\n\n".join(batched_evidence)
    prompt = enrich_market_intelligence_prompt(batched_evidence_text)
    
    try:
        response = call_gemini(prompt)
        raw = response.text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("```").strip()
        data = json.loads(raw)

        for profile in profiles:
            c_name = profile["name"]
            # Try exact match, then case-insensitive match
            c_data = data.get(c_name, data.get(c_name.lower(), {}))
            profile["target_audience"]   = c_data.get("target_audience", "Not enough data")
            profile["value_proposition"] = c_data.get("value_proposition", "Not enough data")
            profile["pricing_model"]     = c_data.get("pricing_model", "Not enough data")
            
    except Exception as exc:
        logger.warning(f"[enrich_market_intelligence] Warning: {exc}")
        for profile in profiles:
            profile["target_audience"]   = "Not enough data"
            profile["value_proposition"] = "Not enough data"
            profile["pricing_model"]     = "Not enough data"

    return {"competitors": profiles}

# ══════════════════════════════════════════════════════════════════════════════
# NODE 2c — Enrich product reality: features, strengths, weaknesses
# ══════════════════════════════════════════════════════════════════════════════
def enrich_product_reality(state: DocumentGeneratorState) -> dict:
    logger.info("--- Node: enrich_product_reality ---")
    profiles = state.get("competitors", [])
    if not profiles:
        return {"competitors": []}

    batched_evidence = []

    for profile in profiles:
        name = profile["name"]
        sw   = profile.get("sw_profile") or ""

        evidence_blocks = []

        q_api = f"{name} API documentation technical capabilities integrations"
        
        review_domain = sw.split("/")[2] if "//" in sw else ""
        if review_domain:
            q_pros = f"{name} pros strengths site:{review_domain}"
        else:
            q_pros = f"{name} pros strengths (site:g2.com OR site:capterra.com)"
            
        q_cons = f"{name} cons problems limitations complaints alternatives why switched"
        
        queries = [q_api, q_pros, q_cons]
        raw_results = execute_serper_search(queries)
        
        # Roughly top 17 results to match the original constraints
        for r in raw_results[:17]:
            snippet = r.get("snippet", "")
            title = r.get("title", "")
            link = r.get("link", "")
            if snippet:
                evidence_blocks.append(f"[{title}] ({link})\n{snippet}")

        evidence_text = "\n\n".join(evidence_blocks) if evidence_blocks else "No evidence found."
        batched_evidence.append(f"### Competitor: {name}\n{evidence_text}")
        
    batched_evidence_text = "\n\n---\n\n".join(batched_evidence)
    prompt = enrich_product_reality_prompt(batched_evidence_text)
    
    try:
        response = call_gemini(prompt)
        raw = response.text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("```").strip()
        data = json.loads(raw)

        for profile in profiles:
            c_name = profile["name"]
            c_data = data.get(c_name, data.get(c_name.lower(), {}))
            profile["core_features"] = c_data.get("core_features", "Not enough data")
            profile["strengths"]     = c_data.get("strengths", "Not enough data")
            profile["weaknesses"]    = c_data.get("weaknesses", "Not enough data")
            
    except Exception as exc:
        logger.warning(f"[enrich_product_reality] Warning: {exc}")
        for profile in profiles:
            profile["core_features"] = "Not enough data"
            profile["strengths"]     = "Not enough data"
            profile["weaknesses"]    = "Not enough data"

    return {"competitors": profiles}

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
    md += "| Competitor | Type | HQ Location | Target Audience | Value Proposition | Pricing Model | Core Features | Strengths | Weaknesses | Website | Review Profile | LinkedIn |\n"
    md += "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    
    for p in sorted_profiles:
        name = p.get("name", "N/A")
        ctype = str(p.get("competitor_type", "N/A")).capitalize()
        hq = p.get("physical_location") or "Unknown"
        aud = p.get("target_audience", "N/A").replace("|", "-").replace("\n", " ")
        val_prop = p.get("value_proposition", "N/A").replace("|", "-").replace("\n", " ")
        pricing = p.get("pricing_model", "N/A").replace("|", "-").replace("\n", " ")
        feats = p.get("core_features", "N/A").replace("|", "-").replace("\n", " ")
        strn = p.get("strengths", "N/A").replace("|", "-").replace("\n", " ")
        weak = p.get("weaknesses", "N/A").replace("|", "-").replace("\n", " ")
        
        web = p.get("company_website")
        web_link = f"[Website]({web})" if web else "N/A"
        
        sw = p.get("sw_profile")
        sw_link = f"[Profile]({sw})" if sw else "N/A"
        
        li = p.get("linkedin_url")
        li_link = f"[LinkedIn]({li})" if li else "N/A"
        
        md += f"| {name} | **{ctype}** | {hq} | {aud} | {val_prop} | {pricing} | {feats} | {strn} | {weak} | {web_link} | {sw_link} | {li_link} |\n"
        
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
