"""
tools.py
--------
External tool integrations for the recommendation agent.
Tavily Search API + World Bank API.
"""

import requests
from typing import Dict, Any, List
from app.utils.logger import logger
try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

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

def analyze_wb_indicator(indicator: str, value: float) -> str:
    """Map WB indicator values to risk levels based on hardcoded thresholds."""
    if value is None:
        return "unknown"
        
    if indicator == "inflation_rate":
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
                        risk = analyze_wb_indicator(name, value)
                        results[name] = {"value": round(value, 2), "risk": risk}
        except Exception as e:
            logger.warning(f"Failed to fetch {name} for {country_iso} from World Bank: {e}")
            
    return results

def fetch_tavily_news(country: str, sector: str, stage: str, api_key: str) -> List[Dict[str, Any]]:
    """Fetch targeted market intelligence from Tavily API."""
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
        if country and sector:
            queries.extend([
                f"{country} startup investment climate 2025",
                f"{sector} funding {country} 2025",
                f"{country} business regulation 2025"
            ])
        elif country:
            queries.extend([
                 f"{country} startup investment climate 2025",
                 f"{country} business regulation changes 2025"
            ])
        elif sector:
            queries.extend([
                f"global {sector} startup funding trends 2025"
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

def run_market_intel(insights: Dict[str, Any], tavily_api_key: str = None) -> Dict[str, Any]:
    """
    Run market intelligence gathering by calling World Bank and Tavily APIs.
    Synthesizes findings into risk flags and calculates an overall context confidence score.
    """
    country = insights.get("country", "").strip() if insights.get("country") else ""
    sector = insights.get("sector", "").strip() if insights.get("sector") else ""
    stage = insights.get("stage", "")
    
    country_iso = COUNTRY_TO_ISO2.get(country.lower()) if country else None
    
    # 1. Fetch Data
    country_risk = fetch_world_bank_data(country_iso) if country_iso else {}
    news_signals = fetch_tavily_news(country, sector, stage, tavily_api_key)
    
    # 2. Synthesize Risk Flags
    risk_flags = []
    high_wb_count = sum(1 for data in country_risk.values() if data.get("risk") == "high")
    
    # Check for keywords in news snippets
    danger_keywords = ["crisis", "capital controls", "ban", "devaluation", "sanctions", "crackdown", "default", "bankruptcy"]
    news_flags_count = 0
    
    for news in news_signals:
        snippet_lower = news.get("snippet", "").lower()
        title_lower = news.get("title", "").lower()
        
        matched_keywords = [k for k in danger_keywords if k in snippet_lower or k in title_lower]
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
    confidence = "high" if sources_count == 3 else "medium" if sources_count == 2 else "low"
    
    return {
        "country_risk": country_risk,
        "news_signals": news_signals,
        "risk_flags": risk_flags,
        "funding_climate": funding_climate,
        "confidence": confidence,
        "sources_used": [s for s, b in [("World Bank", bool(country_risk)), ("Tavily Search", bool(news_signals))] if b]
    }
