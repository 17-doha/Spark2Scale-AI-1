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

def _search_one(query: str, num: int = 5) -> list:
    """
    Wraps execute_serper_search for a SINGLE isolated query.
 
    execute_serper_search accepts a list of queries and returns a flat merged
    list with no way to tell which result came from which query. Passing
    multiple queries together causes cross-competitor and cross-intent
    contamination (e.g. Pet Care AI results bleeding into Pet Manager's
    website field, Dojo payment API results contaminating Dogo's features).
 
    Always pass exactly one query here and slice to `num` results.
    """
    results = execute_serper_search([query])
    return results[:num]
 
 
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
# NODE 2 — Enrich each competitor with web links via Serper (4 calls/competitor)
# ══════════════════════════════════════════════════════════════════════════════
def enrich_competitor_links(state: DocumentGeneratorState) -> dict:
    """
    Runs 4 separate, intent-specific searches per competitor via _search_one.
 
    WHY NOT BATCH: execute_serper_search merges all query results into one flat
    list, so passing multiple queries contaminates results — a result from the
    Pet Care AI website query can become Pet Manager's company_website because
    the loop hits it first. Each call here is fully isolated.
 
    Call 1 — official website  : filtered to exclude social/review domains
    Call 2 — review profile    : G2 → Capterra → ProductHunt, stops at first hit
    Call 3 — LinkedIn          : targeted query reliably surfaces /company/ URLs
    Call 4 — HQ location       : triggers knowledge panel; broad queries don't
    """
    logger.info("--- Node: enrich_competitor_links ---")
    profiles = state.get("competitors", [])
    updated_profiles = []
 
    exclude_from_site = ("linkedin.", "g2.com", "capterra.", "producthunt.", "crunchbase.")
 
    for profile in profiles:
        name = profile["name"]
 
        # ── Call 1: official website ─────────────────────────────────────────
        site_results = _search_one(f"{name} official website", num=5)
        for r in site_results:
            link = r.get("link", "")
            if not any(ex in link.lower() for ex in exclude_from_site):
                profile["company_website"] = link
                break
 
        # ── Call 2: software review profile ─────────────────────────────────
        # Each review site searched separately — OR queries dilute ranking and
        # the site: operator only works reliably in isolation per query.
        for review_site in ("g2.com", "capterra.com", "producthunt.com"):
            results = _search_one(f"{name} site:{review_site}", num=3)
            for r in results:
                link = r.get("link", "")
                if review_site in link.lower():
                    profile["sw_profile"] = link
                    break
            if profile["sw_profile"]:
                break
 
        # ── Call 3: LinkedIn company page ────────────────────────────────────
        # Dedicated query required — a broad search buries /company/ URLs
        # under /in/ personal profiles and /jobs/ pages.
        li_results = _search_one(f"{name} company LinkedIn", num=5)
        for r in li_results:
            link = r.get("link", "")
            if "linkedin.com/company" in link.lower():
                profile["linkedin_url"] = link
                break
 
        # ── Call 4: HQ location ──────────────────────────────────────────────
        # This query reliably triggers Serper's knowledge panel answer box
        # which contains structured city/country data. Confirmed that broad
        # identity searches do not trigger the panel for most competitors.
        loc_results = _search_one(f"{name} company headquarters location", num=5)
        for r in loc_results:
            snippet = r.get("snippet", "")
            if not snippet:
                continue
            match = re.search(
                r"(?:headquartered|based|located|hq)\s+in\s+([A-Z][^,.]{2,40}(?:,\s*[A-Z][^,.]{2,30})?)",
                snippet,
                re.IGNORECASE,
            )
            if match:
                profile["physical_location"] = match.group(1).strip()
                break
 
        updated_profiles.append(profile)
 
    return {"competitors": updated_profiles}
 
 
# ══════════════════════════════════════════════════════════════════════════════
# NODE 2b — Market intelligence: audience, value prop, pricing (1 call/competitor)
# ══════════════════════════════════════════════════════════════════════════════
def enrich_market_intelligence(state: DocumentGeneratorState) -> dict:
    """
    1 Serper call per competitor via _search_one (isolated, not batched).
    A broad query reliably surfaces pricing pages, review snippets, and about
    pages together for this intent — confirmed no regression vs 3 separate calls.
    All competitor evidence is then batched into a single Gemini call.
    """
    logger.info("--- Node: enrich_market_intelligence ---")
    profiles = state.get("competitors", [])
    if not profiles:
        return {"competitors": []}
 
    batched_evidence = []
 
    for profile in profiles:
        name = profile["name"]
        site = profile.get("company_website") or ""
 
        # One broad query per competitor, results kept isolated via _search_one
        results = _search_one(
            f"{name} pricing plans who is it for target customers review", num=8
        )
        evidence_blocks = [
            f"[{r.get('title','')}] ({r.get('link','')})\n{r['snippet']}"
            for r in results if r.get("snippet")
        ]
        evidence_text = "\n\n".join(evidence_blocks) or "No evidence found."
        batched_evidence.append(
            f"### Competitor: {name}\nWebsite: {site}\n{evidence_text}"
        )
 
    batched_evidence_text = "\n\n---\n\n".join(batched_evidence)
    prompt = enrich_market_intelligence_prompt(batched_evidence_text)
 
    try:
        response = call_gemini(prompt)
        raw = response.text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("```").strip()
        data = json.loads(raw)
 
        for profile in profiles:
            c_name = profile["name"]
            c_data = data.get(c_name, data.get(c_name.lower(), {}))
            profile["target_audience"]   = c_data.get("target_audience",   "Not enough data")
            profile["value_proposition"] = c_data.get("value_proposition", "Not enough data")
            profile["pricing_model"]     = c_data.get("pricing_model",     "Not enough data")
 
    except Exception as exc:
        logger.warning(f"[enrich_market_intelligence] Warning: {exc}")
        for profile in profiles:
            profile["target_audience"]   = "Not enough data"
            profile["value_proposition"] = "Not enough data"
            profile["pricing_model"]     = "Not enough data"
 
    return {"competitors": profiles}
 
 
# ══════════════════════════════════════════════════════════════════════════════
# NODE 2c — Product reality: features, strengths, weaknesses (3 calls/competitor)
# ══════════════════════════════════════════════════════════════════════════════
def enrich_product_reality(state: DocumentGeneratorState) -> dict:
    """
    3 separate Serper calls per competitor via _search_one, each with a
    distinct intent. Kept separate because:
 
    - Call A (API/docs): technical doc pages are buried in mixed-intent queries
    - Call B (review pros): a broad query dilutes the G2/Capterra moat signal
      with marketing pages; must be targeted to the review domain
    - Call C (complaints): mixing positive + negative intent causes search
      engines to suppress complaint/alternatives pages entirely
 
    All competitor evidence is then batched into a single Gemini call.
    """
    logger.info("--- Node: enrich_product_reality ---")
    profiles = state.get("competitors", [])
    if not profiles:
        return {"competitors": []}
 
    batched_evidence = []
 
    for profile in profiles:
        name = profile["name"]
        sw   = profile.get("sw_profile") or ""
        site = profile.get("company_website") or ""
 
        # Extract the bare domain for query anchoring (e.g. "dogopet.com")
        # Anchoring the technical query to the known domain prevents name-collision
        # contamination — e.g. "Dogo API" matching "Dojo" payment API docs.
        site_domain = site.split("/")[2] if "//" in site else ""
 
        evidence_blocks = []
 
        # ── Call A: features / technical depth ───────────────────────────────
        # Use the competitor's website domain as an anchor when available so
        # search engines resolve the correct product, not a similarly-named one.
        # Fall back to a product-category hint ("app", "software", "platform")
        # which also helps disambiguate from unrelated brands.
        if site_domain:
            tech_query = f"{name} features capabilities site:{site_domain}"
        else:
            tech_query = f"{name} app features capabilities how it works"
        tech_results = _search_one(tech_query, num=6)
        for r in tech_results:
            if r.get("snippet"):
                evidence_blocks.append(
                    f"[FEATURES] {r.get('title','')} ({r.get('link','')})\n{r['snippet']}"
                )
 
        # ── Call B: strengths — review site signal ───────────────────────────
        # Drop the word "pros" from the query — many review pages don't use
        # that exact term in their indexed snippets, causing zero results.
        # Instead query for reviews generally; Gemini extracts strengths from
        # whatever positive language appears in the snippets.
        review_domain = sw.split("/")[2] if "//" in sw else ""
        if review_domain:
            pros_query = f"{name} review site:{review_domain}"
        else:
            # No known review page — fall back to a broad user-review search
            pros_query = f"{name} review user experience what users like"
        pros_results = _search_one(pros_query, num=6)
        for r in pros_results:
            if r.get("snippet"):
                evidence_blocks.append(
                    f"[REVIEW] {r.get('title','')} ({r.get('link','')})\n{r['snippet']}"
                )
 
        # ── Call C: complaints / alternatives — weakness signal ──────────────
        cons_results = _search_one(
            f"{name} cons problems limitations complaints alternatives", num=6
        )
        for r in cons_results:
            if r.get("snippet"):
                evidence_blocks.append(
                    f"[WEAKNESSES/CONS] {r.get('title','')} ({r.get('link','')})\n{r['snippet']}"
                )
 
        evidence_text = "\n\n".join(evidence_blocks) or "No evidence found."
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
            profile["strengths"]     = c_data.get("strengths",     "Not enough data")
            profile["weaknesses"]    = c_data.get("weaknesses",    "Not enough data")
 
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
 
    comps_listing = "\n".join([
        f"- {p['name']} (Website: {p.get('company_website') or 'unknown'})"
        for p in profiles
    ])
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
            comp_type = classification_dict.get(
                c_name, classification_dict.get(c_name.lower(), "indirect")
            )
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
        name     = p.get("name", "N/A")
        ctype    = str(p.get("competitor_type", "N/A")).capitalize()
        hq       = p.get("physical_location") or "Unknown"
        aud      = (p.get("target_audience")    or "N/A").replace("|", "-").replace("\n", " ")
        val_prop = (p.get("value_proposition")  or "N/A").replace("|", "-").replace("\n", " ")
        pricing  = (p.get("pricing_model")      or "N/A").replace("|", "-").replace("\n", " ")
        feats    = (p.get("core_features")      or "N/A").replace("|", "-").replace("\n", " ")
        strn     = (p.get("strengths")          or "N/A").replace("|", "-").replace("\n", " ")
        weak     = (p.get("weaknesses")         or "N/A").replace("|", "-").replace("\n", " ")
 
        web   = p.get("company_website")
        sw    = p.get("sw_profile")
        li    = p.get("linkedin_url")
 
        web_link = f"[Website]({web})" if web else "N/A"
        sw_link  = f"[Profile]({sw})"  if sw  else "N/A"
        li_link  = f"[LinkedIn]({li})" if li  else "N/A"
 
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
        "competitor_analysis_document": {"json_data": sorted_profiles, "status": "completed"}
    }