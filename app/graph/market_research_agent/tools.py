import os
import json
import http.client
import pandas as pd
import platform
import glob
from app.core.logger import get_logger
from app.graph.market_research_agent.research_config import ResearchConfig

# Helper Imports - UPDATED to use improved versions
from .helpers import research_utils, market_utils, finance_utils, pdf_utils
from .helpers import validator_utils  # This will be the improved version
from .helpers.market_sizing_validator import RealisticMarketSizer  # NEW

logger = get_logger("MarketResearchTools")

# ==========================================
# 3. Research Engine (Competitors)
# ==========================================
def find_competitors(business_idea: str):
    # FALLBACK for legacy calls
    logger.info(f"\n🕵️ [Tool 3] Deep Market Research (Enhanced Mode) for: '{business_idea}'...")
    queries = research_utils.generate_smart_queries(business_idea)
    return _execute_competitor_search(business_idea, queries)

def find_competitors_from_plan(business_idea: str, plan: dict):
    logger.info(f"\n🕵️ [Tool 3] Deep Market Research (Plan Mode) for: '{business_idea}'...")
    queries = plan.get("competitor_queries", [f"{business_idea} alternatives"])
    return _execute_competitor_search(business_idea, queries)

def _execute_competitor_search(business_idea, queries):
    # Use configured limit instead of hardcoded 2
    max_queries = ResearchConfig.MAX_COMPETITOR_QUERIES
    logger.info(f"   📊 Using up to {max_queries} competitor queries for better coverage...")
    
    all_raw_results = research_utils.execute_serper_search(queries[:max_queries])
    
    if not all_raw_results: 
        logger.warning("   ⚠️ No competitor search results found.")
        return None
        
    # AI Extraction
    competitors = research_utils.extract_competitors_strict(all_raw_results, business_idea)
    
    if competitors:
        os.makedirs("data_output", exist_ok=True)
        filename = f"data_output/{business_idea.replace(' ', '_')}_competitors.csv"
        
        try:
            df = pd.DataFrame(competitors)
            if "Features" not in df.columns: 
                df["Features"] = "Standard Features"
            df.to_csv(filename, index=False)
            logger.info(f"✅ Success: Extracted {len(df)} VALID competitors.")
            return filename
        except Exception as e:
            logger.error(f"DataFrame Error: {e}")
            return None
    else:
        logger.warning("   ⚠️ No competitors extracted from search results.")
    return None

# ==========================================
# 4. Problem Validator (ENHANCED)
# ==========================================
def validate_problem(idea, problem_statement, plan=None):
    logger.info(f"\n😤 [Tool 6] Validating Problem with Enhanced Multi-Source Search...")
    
    # Generate or use planned queries
    if plan and "validation_queries" in plan:
        queries = plan["validation_queries"]
    else:
        queries = validator_utils.generate_validation_queries(idea, problem_statement)
        
    if not queries:
        logger.warning("⚠️ Validation queries missing. Skipping validation.")
        return None
    
    logger.info(f"   📋 Validation Plan: {ResearchConfig.MAX_VALIDATION_QUERIES_PER_TYPE} queries per category across {len(ResearchConfig.VALIDATION_SOURCES)} sources")
    
    # NEW: Use multi-source search
    evidence_list = validator_utils.search_multiple_sources(queries, idea)
    
    if not evidence_list:
        logger.warning("⚠️ No validation evidence found across any source.")
        # Create minimal result indicating insufficient data
        minimal_result = {
            "verdict": "INSUFFICIENT_DATA",
            "pain_score": 0,
            "pain_score_explanation": "No evidence found to validate problem",
            "confidence": "None",
            "warnings": ["No evidence sources found. Cannot validate problem."],
            "evidence_quality": {
                "total_count": 0,
                "quality_level": "none"
            }
        }
        
        os.makedirs("data_output", exist_ok=True)
        with open(f"data_output/{idea.replace(' ', '_')}_validation.json", "w") as f:
            json.dump(minimal_result, f, indent=4)
        
        return f"data_output/{idea.replace(' ', '_')}_validation.json"

    # NEW: Enhanced analysis with evidence quality scoring
    analysis = validator_utils.analyze_pain_points(idea, problem_statement, evidence_list)
    
    if not analysis:
        logger.warning("⚠️ Validation analysis failed.")
        return None

    # Save enhanced validation results
    os.makedirs("data_output", exist_ok=True)
    output_file = f"data_output/{idea.replace(' ', '_')}_validation.json"
    
    with open(output_file, "w") as f:
        json.dump(analysis, f, indent=4)
    
    # Enhanced logging
    logger.info(f"   ⚖️  VERDICT: {analysis.get('verdict')}")
    logger.info(f"   🩸 PAIN SCORE: {analysis.get('pain_score'):.1f}/100 (Raw LLM: {analysis.get('pain_score_raw')})")
    logger.info(f"   📊 CONFIDENCE: {analysis.get('confidence')}")
    logger.info(f"   📚 EVIDENCE: {analysis.get('evidence_quality', {}).get('total_count', 0)} sources")
    
    if analysis.get('warnings'):
        logger.warning(f"   ⚠️  WARNINGS:")
        for warning in analysis['warnings']:
            logger.warning(f"      - {warning}")
    
    return output_file

# ==========================================
# 5. Market Quantifier (Trends)
# ==========================================
def fetch_trend_data(keywords, geo_code='EG', plan=None):
    logger.info(f"\n📊 [Tool 7] Quantifying Market Demand...")
    
    search_term = keywords[0]
    if plan and "market_identity" in plan:
        wiki_topic = plan["market_identity"].get("wikipedia_topic")
        if wiki_topic: 
            search_term = wiki_topic

    data, source_name = market_utils.get_trending_data([search_term], geo_code)
    
    if data is None:
        topic = search_term
        if not plan:
            topic = market_utils.search_wikidata(search_term)
        data, source_name = market_utils.fetch_wikipedia_data(topic)

    if data is not None and not data.empty:
        col = data.columns[0]
        growth_pct = market_utils.plot_trends(data, source_name, col)
        
        logger.info(f"✅ Success: Growth calculated at {growth_pct:.1f}%")
        return "data_output/market_trends.csv", "data_output/market_demand_chart.png"
        
    logger.warning("⚠️ No trend data available.")
    return None, None

# ==========================================
# 5b. Market Sizing (FIXED WITH REALISTIC TAM/SAM/SOM)
# ==========================================
def calculate_market_size(idea, location="Global", plan=None):
    """
    FIXED VERSION: Calculate TAM/SAM/SOM with realistic validation and correction
    """
    logger.info(f"\n📐 [Tool 11] Calculating REALISTIC TAM/SAM/SOM with Validation...")
    
    # Get industry and location from plan
    industry = "Unknown"
    competitor_count = 5  # Default
    
    if plan and "market_identity" in plan:
        industry = plan["market_identity"].get("industry", "Business")
        location = plan["market_identity"].get("target_country", location)
    else:
        industry = market_utils.identify_industry(idea)
    
    # Get actual competitor count from earlier analysis
    competitors_file = glob.glob(f"data_output/{idea.replace(' ', '_')}_competitors.csv")
    if competitors_file:
        try:
            df = pd.read_csv(competitors_file[0])
            competitor_count = len(df)
            logger.info(f"   🏢 Found {competitor_count} competitors")
        except:
            competitor_count = 5
    
    logger.info(f"   🌍 Analyzing '{industry}' market in {location}...")
    
    # Use configured limit for searches
    max_queries = ResearchConfig.MAX_MARKET_SIZE_QUERIES
    
    queries = [
        f"{industry} market size revenue {location} 2024",
        f"{industry} TAM SAM analysis {location}",
        f"total addressable market {industry} statistics"
    ]
    
    market_data = ""
    for q in queries[:max_queries]:
        logger.info(f"   🔍 Query: {q}")
        market_data += market_utils.search_market_reports(q) + "\n"

    # Get LLM analysis (might have unrealistic numbers)
    result = market_utils.analyze_market_size(idea, industry, location, market_data)

    if not result:
        logger.warning("⚠️ Market sizing analysis failed.")
        return None

    # ========================================
    # APPLY REALISTIC CORRECTIONS (NEW!)
    # ========================================
    
    # Extract raw LLM values
    raw_tam = result.get('tam_value', 'Unknown')
    raw_sam = result.get('sam_value', 'Unknown')
    raw_som = result.get('som_value', 'Unknown')
    
    logger.info(f"   📊 LLM Raw Output:")
    logger.info(f"      TAM: {raw_tam}")
    logger.info(f"      SAM: {raw_sam}")
    logger.info(f"      SOM: {raw_som}")
    
    # Step 1: Validate and correct TAM
    tam_millions, tam_correction = RealisticMarketSizer.validate_and_correct_tam(
        raw_tam, industry, location
    )
    
    if tam_correction:
        logger.warning(f"   ⚠️ TAM CORRECTED: {tam_correction}")
    
    # Step 2: Calculate realistic SAM based on geography
    sam_millions, sam_reasoning = RealisticMarketSizer.calculate_realistic_sam(
        tam_millions, location
    )
    
    # Step 3: Determine market structure from competitor count
    market_structure = RealisticMarketSizer.determine_market_structure(competitor_count)
    logger.info(f"   🏗️  Market Structure: {market_structure} ({competitor_count} competitors)")
    
    # Step 4: Calculate realistic SOM based on competition
    som_millions, som_reasoning = RealisticMarketSizer.calculate_realistic_som(
        sam_millions, market_structure, has_funding=False
    )
    
    # Step 5: Format corrected values
    corrected_tam = RealisticMarketSizer.format_value(tam_millions)
    corrected_sam = RealisticMarketSizer.format_value(sam_millions)
    corrected_som = RealisticMarketSizer.format_value(som_millions)
    
    logger.info(f"   ✅ CORRECTED Output:")
    logger.info(f"      TAM: {corrected_tam}")
    logger.info(f"      SAM: {corrected_sam}")
    logger.info(f"      SOM: {corrected_som}")
    
    # Step 6: Update result with corrected values
    result['tam_value'] = corrected_tam
    result['sam_value'] = corrected_sam
    result['som_value'] = corrected_som
    
    # Update descriptions with corrections
    if tam_correction:
        result['tam_description'] = result.get('tam_description', '') + f" [CORRECTED: {tam_correction}]"
    
    result['sam_description'] = sam_reasoning
    result['som_description'] = som_reasoning
    result['market_structure'] = market_structure
    result['corrections_applied'] = [tam_correction] if tam_correction else []
    
    # Add raw values for transparency
    result['raw_values'] = {
        "raw_tam": raw_tam,
        "raw_sam": raw_sam,
        "raw_som": raw_som
    }
    
    # Generate Visual
    market_utils.plot_market_funnel(result, industry)
    
    # Save JSON
    with open("data_output/market_sizing.json", "w") as f:
        json.dump(result, f, indent=4)
    
    # Final logging
    logger.info(f"   📊 Market Type: {result.get('market_type')}")
    logger.info(f"   ✅ Data Quality: {result.get('data_quality')}")
    
    if result.get('corrections_applied'):
        logger.warning(f"   ⚠️ Corrections were applied to ensure realistic numbers")
    
    return "data_output/market_sizing.json"

# ==========================================
# 6. Finance Model
# ==========================================
def run_finance_model(idea, plan=None):
    logger.info(f"\n💰 [Tool 8] Starting Enhanced Financial Model...")
    
    if plan and "financial_queries" in plan:
        currency = plan["market_identity"].get("currency_code", "USD")
        queries = plan.get("financial_queries", [])
        
        # Use configured limit
        max_queries = ResearchConfig.MAX_FINANCE_QUERIES
        logger.info(f"   📊 Using up to {max_queries} finance queries...")
        
        market_data = ""
        for q in queries[:max_queries]:
            market_data += finance_utils.search_cost_data(q) + "\n"
            
        estimates = finance_utils.generate_financial_estimates(idea, market_data, currency)
    else:
        # Optimization: Pass market_identity if available to skip currency detection
        currency_context = plan.get("market_identity") if plan else None
        estimates = finance_utils.get_real_world_estimates(idea, currency_context=currency_context)
        
    if not estimates:
        logger.warning("⚠️ Financial estimation failed.")
        return None

    return finance_utils.generate_financial_visuals(estimates)

# ==========================================
# 7. Report Generator (Uses improved pdf_utils)
# ==========================================
def generate_report(file_path, query, trend_file=None, finance_file=None):
    return pdf_utils.generate_report(file_path, query, trend_file, finance_file)

# ==========================================
# 8. PDF Compiler (Unchanged - uses files generated above)
# ==========================================
def compile_final_pdf(idea_name):
    """
    Delegate PDF generation to the full implementation in pdf_utils
    """
    return pdf_utils.compile_final_pdf_report(idea_name)

def compile_final_json(idea_name):
    logger.info(f"\n💾 [Tool 10] Compiling JSON Data Output...")
    
    json_data = {
        "idea_name": idea_name,
        "executive_summary": "",
        "opportunity_analysis": {},
        "market_sizing": {},
        "competitors": [],
        "validation": {},
        "finance": {},
        "trends": {}
    }

    # Executive Summary
    if os.path.exists("data_output/FINAL_MARKET_REPORT.md"):
        with open("data_output/FINAL_MARKET_REPORT.md", "r", encoding="utf-8") as f:
            json_data["executive_summary"] = f.read()

    # Opportunity Analysis
    if os.path.exists("data_output/opportunity_analysis.json"):
        with open("data_output/opportunity_analysis.json", "r") as f:
            json_data["opportunity_analysis"] = json.load(f)

    # Market Sizing (NOW WITH CORRECTIONS)
    if os.path.exists("data_output/market_sizing.json"):
        with open("data_output/market_sizing.json", "r") as f:
            json_data["market_sizing"] = json.load(f)

    # Competitors
    comp_file = f"data_output/{idea_name.replace(' ', '_')}_competitors.csv"
    if os.path.exists(comp_file):
        try:
            df = pd.read_csv(comp_file)
            json_data["competitors"] = df.to_dict(orient="records")
        except Exception as e:
            logger.error(f"Error reading competitors: {e}")

    # Validation
    val_file = f"data_output/{idea_name.replace(' ', '_')}_validation.json"
    if os.path.exists(val_file):
        with open(val_file, "r") as f:
            json_data["validation"] = json.load(f)

    # Finance
    if os.path.exists("data_output/finance_estimates.json"):
        with open("data_output/finance_estimates.json", "r") as f:
            json_data["finance"] = json.load(f)

    # Trends
    if os.path.exists("data_output/market_stats.csv"):
        try:
            df = pd.read_csv("data_output/market_stats.csv")
            json_data["trends"] = df.to_dict(orient="records")
        except Exception as e:
            logger.error(f"Error reading trends: {e}")
            
    try:
        clean_name = idea_name.replace(' ', '_').replace('"', '').replace("'", "")
        output_filename = f"data_output/{clean_name}_Market_Report.json"
        
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=4)
            
        logger.info(f"✅ JSON GENERATED: {output_filename}")
        return output_filename
    except Exception as e:
        logger.error(f"❌ JSON Compilation Failed: {e}")
        return None
