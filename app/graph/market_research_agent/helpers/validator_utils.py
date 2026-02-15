import json
import http.client
import os
import re
from datetime import datetime, timedelta
from app.core.config import Config, gemini_client
from app.core.rate_limiter import call_gemini
from app.graph.market_research_agent import prompts
from app.graph.market_research_agent.logger_config import get_logger
from app.graph.market_research_agent.research_config import ResearchConfig, get_evidence_quality

logger = get_logger("ValidatorUtils")

SERPER_API_KEY = Config.SERPER_API_KEY

def extract_json_from_text(text):
    """
    Extracts the first valid JSON block from a string, handling markdown code blocks.
    """
    try:
        # 1. Try to find content within ```json ... ``` blocks
        match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        
        # 2. Try to find content within curly braces { ... }
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
            
        # 3. Fallback: try raw text if it looks like JSON
        return json.loads(text)
    except Exception as e:
        logger.warning(f"JSON Extraction Failed: {e}")
        return None

def search_forums(query):
    try:
        conn = http.client.HTTPSConnection("google.serper.dev")
        payload = json.dumps({ "q": query, "num": ResearchConfig.SEARCH_RESULTS_PER_QUERY })
        headers = { 'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json' }
        conn.request("POST", "/search", payload, headers)
        return json.loads(conn.getresponse().read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"Forum search error: {e}")
        return {}

def generate_validation_queries(idea, problem_statement):
    try:
        prompt = prompts.generate_validation_queries_prompt(idea, problem_statement)
        res = call_gemini(prompt)
        return extract_json_from_text(res.text)
    except Exception as e: 
        logger.warning(f"Validation query generation error: {e}")
        return None

def search_multiple_sources(queries_dict, idea):
    """
    Search across multiple platforms for better validation coverage
    
    Args:
        queries_dict: Dict with 'problem' and 'solution' query lists
        idea: Business idea name
    
    Returns:
        List of evidence with metadata
    """
    all_evidence = []
    
    # Problem queries - search across multiple sources
    prob_queries = queries_dict.get("problem_queries", []) or queries_dict.get("problem", [])
    sol_queries = queries_dict.get("solution_queries", []) or queries_dict.get("solution", [])
    
    logger.info(f"   🔍 Searching {len(prob_queries)} problem queries and {len(sol_queries)} solution queries...")
    
    # Use configured limits instead of hardcoded values
    max_queries = ResearchConfig.MAX_VALIDATION_QUERIES_PER_TYPE
    
    # Search problem evidence across multiple platforms
    for q in prob_queries[:max_queries]:
        for source in ResearchConfig.VALIDATION_SOURCES:
            site = source["site"]
            weight = source["weight"]
            credibility = source["credibility"]
            
            search_query = f"site:{site} {q}"
            logger.info(f"   📱 Searching {site} for: {q}")
            
            res = search_forums(search_query)
            if "organic" in res:
                for item in res["organic"]:
                    all_evidence.append({
                        "type": "PROBLEM",
                        "title": item.get('title', ''),
                        "snippet": item.get('snippet', ''),
                        "link": item.get('link', ''),
                        "source": site,
                        "weight": weight,
                        "credibility": credibility,
                        "date": item.get('date', 'unknown')  # Some APIs provide this
                    })
    
    # Search solution evidence (existing alternatives/competitors)
    for q in sol_queries[:max_queries]:
        for source in ResearchConfig.VALIDATION_SOURCES[:3]:  # Limit solution searches
            site = source["site"]
            weight = source["weight"]
            credibility = source["credibility"]
            
            search_query = f"site:{site} {q}"
            logger.info(f"   🔍 Searching {site} for: {q}")
            
            res = search_forums(search_query)
            if "organic" in res:
                for item in res["organic"]:
                    all_evidence.append({
                        "type": "SOLUTION",
                        "title": item.get('title', ''),
                        "snippet": item.get('snippet', ''),
                        "link": item.get('link', ''),
                        "source": site,
                        "weight": weight,
                        "credibility": credibility,
                        "date": item.get('date', 'unknown')
                    })
    
    logger.info(f"   ✅ Found {len(all_evidence)} pieces of evidence across {len(set(e['source'] for e in all_evidence))} sources")
    return all_evidence

def analyze_evidence_quality(evidence_list):
    """
    Analyze the quality and distribution of evidence
    
    Returns:
        Dict with quality metrics
    """
    if not evidence_list:
        return {
            "total_count": 0,
            "quality_level": "minimal",
            "quality_multiplier": 0.3,
            "source_diversity": 0,
            "credibility_score": 0
        }
    
    total_count = len(evidence_list)
    sources = set(e['source'] for e in evidence_list)
    
    # Calculate weighted credibility score
    credibility_scores = {
        "high": 1.0,
        "medium": 0.7,
        "low": 0.4
    }
    
    avg_credibility = sum(
        credibility_scores.get(e['credibility'], 0.5) * e['weight'] 
        for e in evidence_list
    ) / len(evidence_list) if evidence_list else 0
    
    quality_level, quality_multiplier = get_evidence_quality(total_count)
    
    return {
        "total_count": total_count,
        "quality_level": quality_level,
        "quality_multiplier": quality_multiplier,
        "source_diversity": len(sources),
        "credibility_score": round(avg_credibility, 2),
        "problem_evidence_count": sum(1 for e in evidence_list if e['type'] == 'PROBLEM'),
        "solution_evidence_count": sum(1 for e in evidence_list if e['type'] == 'SOLUTION')
    }

def analyze_pain_intensity(evidence_list):
    """
    Analyze pain intensity based on keywords and sentiment in evidence
    
    Returns:
        Float multiplier (0.5 to 1.5)
    """
    if not evidence_list:
        return 1.0
    
    high_pain_count = 0
    low_pain_count = 0
    
    for evidence in evidence_list:
        text = (evidence.get('title', '') + ' ' + evidence.get('snippet', '')).lower()
        
        # Count high pain indicators
        for keyword in ResearchConfig.HIGH_PAIN_KEYWORDS:
            if keyword.lower() in text:
                high_pain_count += 1
        
        # Count low pain indicators
        for keyword in ResearchConfig.LOW_PAIN_KEYWORDS:
            if keyword.lower() in text:
                low_pain_count += 1
    
    # Calculate intensity multiplier
    if high_pain_count > low_pain_count * 2:
        return 1.3  # High intensity signals
    elif low_pain_count > high_pain_count * 2:
        return 0.7  # Low intensity signals
    else:
        return 1.0  # Neutral

def calculate_realistic_pain_score(llm_score, evidence_list):
    """
    Adjust LLM pain score based on actual evidence quality
    
    Args:
        llm_score: Initial score from LLM (0-100)
        evidence_list: List of evidence items with metadata
    
    Returns:
        Adjusted pain score with explanation
    """
    # Get evidence quality metrics
    quality_metrics = analyze_evidence_quality(evidence_list)
    
    # Get pain intensity multiplier
    intensity_multiplier = analyze_pain_intensity(evidence_list)
    
    # Apply evidence quality multiplier
    adjusted_score = llm_score * quality_metrics['quality_multiplier']
    
    # Apply pain intensity multiplier
    adjusted_score = adjusted_score * intensity_multiplier
    
    # Apply credibility adjustment
    credibility_adjustment = 0.8 + (quality_metrics['credibility_score'] * 0.4)  # 0.8 to 1.2
    adjusted_score = adjusted_score * credibility_adjustment
    
    # Ensure score stays in 0-100 range
    adjusted_score = max(0, min(100, adjusted_score))
    
    # Generate explanation
    explanation = f"""Pain Score Calculation:
    - LLM Initial Score: {llm_score}/100
    - Evidence Quality: {quality_metrics['quality_level']} ({quality_metrics['total_count']} sources)
    - Evidence Multiplier: {quality_metrics['quality_multiplier']}
    - Pain Intensity Factor: {intensity_multiplier:.2f}
    - Source Credibility: {quality_metrics['credibility_score']:.2f}
    - Final Adjusted Score: {adjusted_score:.1f}/100
    
    Reasoning: {"Strong evidence base" if quality_metrics['total_count'] >= 5 else "Limited evidence - score reduced for reliability"}
    """
    
    return {
        "adjusted_score": round(adjusted_score, 1),
        "raw_llm_score": llm_score,
        "quality_metrics": quality_metrics,
        "intensity_multiplier": intensity_multiplier,
        "credibility_adjustment": credibility_adjustment,
        "explanation": explanation,
        "confidence": "High" if quality_metrics['total_count'] >= 8 else "Medium" if quality_metrics['total_count'] >= 5 else "Low"
    }

def analyze_pain_points(idea, problem_statement, evidence_list):
    """
    Enhanced pain point analysis with realistic scoring
    
    Args:
        idea: Business idea
        problem_statement: Problem being solved
        evidence_list: List of evidence items (now with metadata)
    
    Returns:
        Dict with verdict, scores, and detailed breakdown
    """
    # Format evidence for LLM (include source and credibility info)
    formatted_evidence = []
    for e in evidence_list:
        source_label = f"[{e['source'].upper()} - {e['credibility'].upper()} CREDIBILITY]"
        formatted_evidence.append(
            f"{source_label} [{e['type']}] {e['title']} - {e['snippet']}"
        )
    
    evidence_text = "\n".join(formatted_evidence) if formatted_evidence else "No evidence found."
    
    # Get LLM analysis
    judge_prompt = prompts.analyze_pain_points_prompt(idea, problem_statement, evidence_text)
    
    try:
        res = call_gemini(judge_prompt)
        llm_analysis = extract_json_from_text(res.text)
        
        if not llm_analysis:
            logger.error("LLM analysis failed to return valid JSON")
            return None
        
        # Get LLM's initial pain score
        llm_pain_score = llm_analysis.get('pain_score', 50)
        
        # Calculate realistic adjusted score
        pain_analysis = calculate_realistic_pain_score(llm_pain_score, evidence_list)
        
        # Quality metrics
        quality_metrics = analyze_evidence_quality(evidence_list)
        
        # Determine verdict with evidence-based logic
        adjusted_score = pain_analysis['adjusted_score']
        evidence_count = quality_metrics['total_count']
        
        # Stricter verdict criteria
        if adjusted_score >= 70 and evidence_count >= 5:
            verdict = "VALIDATED"
        elif adjusted_score >= 50 and evidence_count >= 3:
            verdict = "MODERATE"
        elif evidence_count < ResearchConfig.MIN_VALIDATION_SOURCES:
            verdict = "INSUFFICIENT_DATA"
        else:
            verdict = "WEAK"
        
        # Generate warnings
        warnings = []
        if evidence_count < ResearchConfig.MIN_VALIDATION_SOURCES:
            warnings.append(f"Only {evidence_count} evidence sources found. Minimum {ResearchConfig.MIN_VALIDATION_SOURCES} recommended.")
        
        if quality_metrics['source_diversity'] < 2:
            warnings.append("Evidence from only 1 platform. Cross-platform validation recommended.")
        
        if pain_analysis['confidence'] == "Low":
            warnings.append("Low confidence in pain score due to limited evidence.")
        
        # Compile final analysis
        return {
            "verdict": verdict,
            "pain_score": adjusted_score,
            "pain_score_raw": llm_pain_score,
            "pain_score_explanation": pain_analysis['explanation'],
            "confidence": pain_analysis['confidence'],
            "solution_fit_score": llm_analysis.get('solution_fit_score', 'Unknown'),
            "reasoning": llm_analysis.get('reasoning', 'Analysis completed'),
            "evidence_quality": quality_metrics,
            "warnings": warnings,
            "evidence_samples": [
                {
                    "source": e['source'],
                    "type": e['type'],
                    "title": e['title'][:100],
                    "credibility": e['credibility']
                }
                for e in evidence_list[:10]  # Include top 10 samples
            ]
        }
        
    except Exception as e:
        logger.error(f"⚠️ Pain Analysis Error: {e}")
        return None
