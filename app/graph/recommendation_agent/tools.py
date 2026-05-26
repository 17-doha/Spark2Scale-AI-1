"""
tools.py
--------
External tool integrations for the recommendation agent.
Tavily Search API + World Bank API.
"""

import re
import statistics
import requests
from typing import Dict, Any, List, Optional
from app.utils.logger import logger
try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None


def generate_targeted_intel_query(lowest_category: str, sector: str, stage: str, competitor: str = None) -> str:
    """
    Generates high-credibility, multi-source search queries for the Recommendation Agent.

    Instead of a generic web search, this bundles the industry-standard web footprints
    that matter for a given weakness (e.g. LinkedIn/Crunchbase for Team, G2/Reddit for
    Product, SimilarWeb/Instagram for GTM) so Tavily can triangulate live benchmarks
    against the startup's single weakest evaluation pillar.

    When a real `competitor` name is known, the GTM/Product queries target that
    competitor's specific footprint (e.g. its SimilarWeb/Instagram handle). Without
    one, they fall back to a generic platform search rather than emitting a
    malformed handle like `site:instagram.com/industry leaders`.
    """
    sector = (sector or "startup").strip()
    comp = (competitor or "").strip()
    has_comp = bool(comp) and comp.lower() != "industry leaders"

    if has_comp:
        gtm_query = f"(site:instagram.com/{comp} OR site:similarweb.com/website/{comp}) marketing channels traffic sources content strategy"
        product_query = f"(site:g2.com OR site:producthunt.com OR site:capterra.com) top alternatives to {comp} {sector} reviews features"
    else:
        gtm_query = f"(site:similarweb.com OR site:instagram.com) {sector} startup marketing channels traffic sources content strategy"
        product_query = f"(site:g2.com OR site:producthunt.com OR site:capterra.com) best {sector} software reviews features alternatives"

    queries = {
        "team": f"(site:linkedin.com/in OR site:crunchbase.com/person) successful {sector} startup founders skills background",
        "problem": f"(site:reddit.com OR site:trustpilot.com) biggest complaints negative reviews about {sector} software",
        "product": product_query,
        "market": f"(site:mckinsey.com OR site:statista.com OR site:bain.com) {sector} market size CAGR trends report 2026",
        "traction": f"(site:techcrunch.com OR site:pitchbook.com) Series {stage} {sector} startup revenue active users milestones",
        "gtm": gtm_query,
        "economics": f"(site:saastr.com OR site:openviewpartners.com OR site:chartmogul.com) {sector} benchmarks CAC LTV gross margin",
        "vision": f"(site:a16z.com OR site:ycombinator.com OR site:sequoiacap.com) {sector} economic moat long term vision",
        "ops": f"(site:about.gitlab.com OR site:blog.pragmaticengineer.com) engineering team structure agile {sector} best practices",
    }
    return queries.get((lowest_category or "").lower(), f"{sector} startup best practices industry standards")

# A simple mapping of major MENA + global countries to ISO2 codes
COUNTRY_TO_ISO2 = {
    "egypt": "EG",
    "tunisia": "TN",
    "uae": "AE",
    "united arab emirates": "AE",
    "saudi arabia": "SA",
    "morocco": "MA",
    "jordan": "JO",
    "lebanon": "LB",
    "qatar": "QA",
    "kuwait": "KW",
    "bahrain": "BH",
    "oman": "OM",
    "turkey": "TR",
    "usa": "US",
    "united states": "US",
    "uk": "GB",
    "united kingdom": "GB",
    "france": "FR",
    "germany": "DE",
    "india": "IN",
}

# World Bank Indicators
WB_INDICATORS = {
    "inflation_rate": "FP.CPI.TOTL.ZG",
    "gdp_growth_rate": "NY.GDP.MKTP.KD.ZG",
    "unemployment_rate": "SL.UEM.TOTL.ZS",
    "government_debt_%_of_gdp": "GC.DOD.TOTL.GD.ZS",
    "ease_of_doing_business_score": "IC.BUS.EASE.XQ" # Note: ease of business might be deprecated, but we try
}

def fetch_global_inflation_baseline() -> Optional[Dict[str, float]]:
    """
    Pull the current global inflation distribution from the World Bank API
    (latest value per country) and return its {mean, std, n}.

    This replaces the old hardcoded `inflation > 15` threshold: a country is only
    flagged "high" risk when it sits meaningfully worse than the live global
    baseline (see `analyze_wb_indicator`). Returns None on any failure so callers
    can fall back to static thresholds instead of crashing.

    The `country/all` feed mixes ~217 countries with regional/income aggregates and
    a few hyperinflation economies (Argentina, Sudan, Venezuela at 100–200%+). Those
    extreme values would balloon a plain standard deviation, pushing the 2σ "high"
    cutoff so far out that genuinely high-inflation countries look fine. So we
    IQR-trim outliers before computing the mean/σ, giving a baseline that reflects
    typical economies.
    """
    try:
        url = (
            "https://api.worldbank.org/v2/country/all/indicator/"
            f"{WB_INDICATORS['inflation_rate']}?format=json&mrv=1&per_page=400"
        )
        response = requests.get(url, timeout=8)
        if response.status_code != 200:
            return None
        data = response.json()
        if not isinstance(data, list) or len(data) < 2 or not data[1]:
            return None
        values = [
            float(row["value"])
            for row in data[1]
            if row.get("value") is not None
        ]
        if len(values) < 10:
            return None

        # IQR-trim to drop hyperinflation / aggregate outliers before estimating.
        q1, _, q3 = statistics.quantiles(values, n=4)
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        trimmed = [v for v in values if lo <= v <= hi]
        if len(trimmed) < 10:
            trimmed = values  # too aggressive a trim; fall back to the full set

        return {
            "mean": round(statistics.mean(trimmed), 2),
            "std": round(statistics.pstdev(trimmed), 2),
            "n": len(trimmed),
            "n_raw": len(values),
            "method": "iqr-trimmed",
        }
    except Exception as e:
        logger.warning(f"Failed to fetch global inflation baseline from World Bank: {e}")
        return None


def analyze_wb_indicator(indicator: str, value: float, baseline: Optional[Dict[str, float]] = None) -> str:
    """Map WB indicator values to risk levels.

    For inflation, prefer a dynamic, distribution-relative judgement when a live
    global `baseline` ({mean, std}) is supplied: "high" only if the country is
    >= 2σ worse than the global average, "medium" at >= 1σ. When no baseline is
    available (offline / unit tests), fall back to the historical static
    thresholds so behaviour stays deterministic.
    """
    if value is None:
        return "unknown"

    if indicator == "inflation_rate":
        if baseline and baseline.get("std"):
            mean = baseline["mean"]
            std = baseline["std"]
            if value >= mean + 2 * std: return "high"
            elif value >= mean + std: return "medium"
            else: return "low"
        # Fallback static thresholds (no live global baseline available)
        if value > 15: return "high"
        elif value > 7: return "medium"
        else: return "low"
    elif indicator == "gdp_growth_rate":
        if value < 0: return "high"
        elif value < 2: return "medium"
        else: return "low"
    elif indicator == "unemployment_rate":
        if value > 15: return "high"
        elif value > 8: return "medium"
        else: return "low"
    elif indicator == "government_debt_%_of_gdp":
        if value > 100: return "high"
        elif value > 70: return "medium"
        else: return "low"
    elif indicator == "ease_of_doing_business_score":
        if value > 100: return "high" # Higher rank is worse
        elif value > 50: return "medium"
        else: return "low"
        
    return "unknown"

def fetch_world_bank_data(country_iso: str) -> Dict[str, Any]:
    """Fetch macro indicators from World Bank API."""
    results = {}
    if not country_iso:
        return results

    # Pull the live global inflation distribution once so inflation risk is judged
    # relative to the current world baseline rather than a hardcoded threshold.
    inflation_baseline = fetch_global_inflation_baseline()

    for name, code in WB_INDICATORS.items():
        try:
            url = f"https://api.worldbank.org/v2/country/{country_iso}/indicator/{code}?format=json&mrv=1"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if len(data) > 1 and data[1]:
                    val = data[1][0].get("value")
                    value = float(val) if val is not None else None
                    if value is not None:
                        baseline = inflation_baseline if name == "inflation_rate" else None
                        risk = analyze_wb_indicator(name, value, baseline=baseline)
                        results[name] = {"value": round(value, 2), "risk": risk}
                        if name == "inflation_rate" and inflation_baseline:
                            # Expose the baseline so the report can cite the live
                            # global average instead of an arbitrary cutoff.
                            results[name]["global_baseline"] = inflation_baseline
        except Exception as e:
            logger.warning(f"Failed to fetch {name} for {country_iso} from World Bank: {e}")

    return results

def fetch_tavily_news(country: str, sector: str, stage: str, api_key: str, lowest_category: str = None, competitor: str = None) -> List[Dict[str, Any]]:
    """Fetch targeted market intelligence from Tavily API.

    When `lowest_category` is supplied, the first query is a multi-domain,
    industry-standard footprint search (LinkedIn, G2, SimilarWeb, etc.) aimed at
    the startup's single weakest evaluation pillar — see
    `generate_targeted_intel_query`. The remaining queries cover the macro/funding
    climate as before.
    """
    if not api_key:
        logger.warning("Tavily API key missing. Skipping news fetch.")
        return []

    if not TavilyClient:
        logger.warning("tavily-python not installed. Skipping news fetch.")
        return []

    try:
        client = TavilyClient(api_key=api_key)

        # Build queries based on available information
        queries = []

        # Multi-source benchmark query targeting the weakest pillar (highest leverage).
        if lowest_category:
            queries.append(generate_targeted_intel_query(lowest_category, sector, stage, competitor=competitor))

        if country and sector:
            queries.extend([
                f"{country} startup investment climate 2026",
                f"{sector} funding {country} 2026",
                f"{country} business regulation 2026"
            ])
        elif country:
            queries.extend([
                 f"{country} startup investment climate 2026",
                 f"{country} business regulation changes 2026"
            ])
        elif sector:
            queries.extend([
                f"global {sector} startup funding trends 2026"
            ])

        all_results = []
        seen_urls = set()
        
        for query in queries:
            try:
                # We use search, not extract, because we want relevant snippets
                response = client.search(
                    query=query, 
                    search_depth="advanced",
                    max_results=5,
                    include_domains=[],
                    exclude_domains=[]
                )
                
                if "results" in response:
                    for res in response["results"]:
                        url = res.get("url")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            all_results.append({
                                "title": res.get("title", ""),
                                "url": url,
                                "source_domain": res.get("url", "").split("/")[2] if "//" in url else url.split("/")[0],
                                "snippet": res.get("content", ""),
                                "score": res.get("score", 0)
                            })
            except Exception as qe:
                logger.warning(f"Tavily query '{query}' failed: {qe}")
                
        # Sort by relevance score and keep top 8
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return all_results[:8]
        
    except Exception as e:
        logger.warning(f"Tavily search API failed: {e}")
        return []

def run_market_intel(insights: Dict[str, Any], tavily_api_key: str = None, lowest_category: str = None, competitor: str = None) -> Dict[str, Any]:
    """
    Run market intelligence gathering by calling World Bank and Tavily APIs.
    Synthesizes findings into risk flags and calculates an overall context confidence score.

    `lowest_category` (the startup's weakest evaluation pillar) routes the Tavily
    search toward the industry-standard web footprints that matter most for that
    weakness. The returned `tool_status` distinguishes a tool that ran and found
    nothing from one that was offline/timed out, so the LLM doesn't mistake an API
    failure for "no market data exists".
    """
    country = insights.get("country", "").strip() if insights.get("country") else ""
    sector = insights.get("sector", "").strip() if insights.get("sector") else ""
    stage = insights.get("stage", "")

    country_iso = COUNTRY_TO_ISO2.get(country.lower()) if country else None

    # 1. Fetch Data
    country_risk = fetch_world_bank_data(country_iso) if country_iso else {}
    news_signals = fetch_tavily_news(country, sector, stage, tavily_api_key, lowest_category=lowest_category, competitor=competitor)

    # Safety catch: tell downstream the difference between "ran, found nothing"
    # and "couldn't run" (no key / no country / timeout).
    if not country_iso:
        wb_status = "no_country"
    elif country_risk:
        wb_status = "ok"
    else:
        wb_status = "offline"

    if not tavily_api_key or not TavilyClient:
        tavily_status = "no_key"
    elif news_signals:
        tavily_status = "ok"
    else:
        tavily_status = "offline"
    
    # 2. Synthesize Risk Flags
    risk_flags = []
    high_wb_count = sum(1 for data in country_risk.values() if data.get("risk") == "high")
    
    # Check for keywords in news snippets. Match on whole words only — a naive
    # substring check flags "ban" inside "bank"/"Banque", turning positive banking
    # news into false "BAN" risk signals (and wrongly souring the funding climate).
    danger_keywords = ["crisis", "capital controls", "ban", "devaluation", "sanctions", "crackdown", "default", "bankruptcy"]
    danger_patterns = {k: re.compile(rf"\b{re.escape(k)}\b") for k in danger_keywords}
    news_flags_count = 0

    for news in news_signals:
        snippet_lower = news.get("snippet", "").lower()
        title_lower = news.get("title", "").lower()

        matched_keywords = [k for k, pat in danger_patterns.items() if pat.search(snippet_lower) or pat.search(title_lower)]
        if matched_keywords:
            news_flags_count += 1
            source_domain = news.get("source_domain", "unknown source")
            risk_flags.append(f"News Signal Risk ({matched_keywords[0].upper()}): '{news.get('title')}' - {source_domain}")
            
    # Add WB flags
    for ind, data in country_risk.items():
        if data.get("risk") == "high":
            clean_name = ind.replace("_", " ").title()
            risk_flags.append(f"Macro Risk: High {clean_name} ({data.get('value')}%)")
            
    # Critical combined flag
    if high_wb_count >= 2 and news_flags_count >= 1:
        risk_flags.insert(0, "CRITICAL MACRO RISK ALIGNMENT: Multiple high-risk economic indicators confirmed by recent news events.")
        
    # 3. Assess Funding Climate (simple heuristic based on news signals)
    funding_climate = "Neutral"
    if any("funding round" in n.get("snippet", "").lower() or "raised" in n.get("snippet", "").lower() for n in news_signals):
        funding_climate = "Active"
    if news_flags_count >= 2 or high_wb_count >= 2:
         funding_climate = "Challenging"
         
    # 4. Calculate Confidence
    sources_count = (1 if country_risk else 0) + (1 if news_signals else 0)
    confidence = "high" if sources_count == 2 else "medium" if sources_count == 1 else "low"
    
    return {
        "country_risk": country_risk,
        "news_signals": news_signals,
        "risk_flags": risk_flags,
        "funding_climate": funding_climate,
        "confidence": confidence,
        "tool_status": {"world_bank": wb_status, "tavily": tavily_status},
        "sources_used": [s for s, b in [("World Bank", bool(country_risk)), ("Tavily Search", bool(news_signals))] if b]
    }
