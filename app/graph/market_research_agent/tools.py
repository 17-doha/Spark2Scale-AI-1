import os
import json
import http.client
import pandas as pd
import platform
import glob
from app.graph.market_research_agent.logger_config import get_logger
from app.graph.market_research_agent.research_config import ResearchConfig

# Helper Imports - UPDATED to use improved versions
from .helpers import research_utils, market_utils, finance_utils, pdf_utils
# Import improved validator utils
from .helpers import validator_utils  # This will be the improved version

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

def calculate_market_size(idea, location="Global", plan=None):
    logger.info(f"\n📐 [Tool 11] Calculating TAM, SAM, SOM & Scalability...")
    
    industry = "Unknown"
    if plan and "market_identity" in plan:
        industry = plan["market_identity"].get("industry", "Business")
        location = plan["market_identity"].get("target_country", location)
    else:
        industry = market_utils.identify_industry(idea)
    
    logger.info(f"   🌍 Searching for '{industry}' market data in {location}...")
    
    # Use configured limit instead of just 1 query
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

    result = market_utils.analyze_market_size(idea, industry, location, market_data)

    if not result:
        logger.warning("⚠️ Market sizing analysis failed.")
        return None

    # Generate Visual
    market_utils.plot_market_funnel(result, industry)
    
    # Save JSON
    with open("data_output/market_sizing.json", "w") as f:
        json.dump(result, f, indent=4)
    
    # Log data quality
    data_quality = result.get('data_quality', 'Unknown')
    logger.info(f"   📊 Market Type: {result.get('market_type')}")
    logger.info(f"   ✅ Data Quality: {data_quality}")
    
    if data_quality == "Low":
        logger.warning("   ⚠️ Market sizing based on limited data. Results may be unreliable.")
    
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
# 8. PDF Compiler
# ==========================================
def compile_final_pdf(idea_name):
    logger.info(f"\n📄 [Tool 9] Compiling Professional PDF Report...")
    
    pdf = pdf_utils.PDFReport()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # --- CROSS-PLATFORM FONT LOADING ---
    system_name = platform.system()
    font_path = None
    if system_name == "Windows":
        font_path = r"C:\Windows\Fonts\arial.ttf"
    elif system_name == "Darwin": # Mac
        font_path = "/Library/Fonts/Arial.ttf"
    elif system_name == "Linux":
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    try:
        if font_path and os.path.exists(font_path):
            pdf.add_font("ArialUnicode", style="", fname=font_path)
            pdf.add_font("ArialUnicode", style="B", fname=font_path)
            logger.info(f"   ✅ Loaded System Font: {font_path}")
        else:
            logger.warning("   ⚠️ Custom font not found. Arabic may not render correctly.")
    except Exception as e:
        logger.error(f"   ⚠️ Font Error: {e}")

    # --- PAGE 1: TITLE & EXECUTIVE SUMMARY ---
    pdf.add_page()
    logger.info(f"   📄 Generating Page {pdf.page_no()}: Title & Executive Summary")
    
    # Title Styling
    pdf.set_font_for_content('B', 14)
    pdf.set_text_color(*pdf_utils.PDFReport.COLOR_MOSS)
    pdf.cell(0, 10, "MARKET RESEARCH REPORT", 0, 1, 'C')
    
    pdf.ln(5)
    
    # Idea Name
    pdf.set_font_for_content('B', 20)
    pdf.multi_cell(0, 10, pdf_utils.fix_arabic(idea_name.upper()), 0, 'C')
    
    pdf.ln(5)
    
    # Subtitle
    pdf.set_font_for_content('', 12)
    pdf.set_text_color(*pdf_utils.PDFReport.COLOR_MOSS)
    try:
        pdf.set_font("Helvetica", 'I', 14)
    except:
        pdf.set_font("Arial", 'I', 14)
    pdf.cell(0, 10, "Comprehensive Market Analysis", 0, 1, 'C')
    
    pdf.set_text_color(0, 0, 0)
    pdf.ln(10)
    
    # Read Report
    report_text = "No report text found. Please check generation logs."
    report_path = "data_output/FINAL_MARKET_REPORT.md"
    if os.path.exists(report_path):
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                raw_text = f.read()
                if not raw_text.strip():
                    logger.warning("   ⚠️ Report file exists but is empty.")
                else:
                    report_text = raw_text
        except Exception as e:
            logger.error(f"   ⚠️ Error reading report: {e}")
            report_text = f"Error reading executive summary: {e}"
    else:
        logger.warning(f"   ⚠️ Report file not found at {report_path}")

    pdf.chapter_title("Executive Summary")
    pdf.chapter_body(report_text[:2500] + "...")
    
    # --- PAGE 2: OPPORTUNITY SCORE BREAKDOWN ---
    pdf.add_page()
    logger.info(f"   📄 Generating Page {pdf.page_no()}: Opportunity Score Analysis")
    pdf.chapter_title("Opportunity Score Breakdown")
    
    # Load opportunity analysis
    if os.path.exists("data_output/opportunity_analysis.json"):
        try:
            with open("data_output/opportunity_analysis.json", "r") as f:
                opp_data = json.load(f)
            
            score = opp_data.get('opportunity_score', 0)
            grade = opp_data.get('grade', 'Unknown')
            confidence = opp_data.get('confidence', 'Unknown')
            breakdown = opp_data.get('breakdown', {})
            
            # Main Score Display
            pdf.set_font_for_content('B', 16)
            
            # Color based on grade
            if 'A' in grade:
                color = (0, 150, 0)  # Green
            elif 'B' in grade:
                color = (50, 100, 200)  # Blue
            elif 'C' in grade:
                color = (200, 150, 0)  # Orange
            else:
                color = (200, 50, 50)  # Red
            
            pdf.set_text_color(*color)
            pdf.cell(0, 10, f"Overall Score: {score}/100 - {grade}", 0, 1, 'C')
            pdf.set_text_color(0, 0, 0)
            
            pdf.set_font_for_content('', 11)
            pdf.cell(0, 8, f"Confidence Level: {confidence}", 0, 1, 'C')
            pdf.ln(5)
            
            # Component Scores
            pdf.set_font_for_content('B', 12)
            pdf.set_text_color(*pdf_utils.PDFReport.COLOR_MOSS)
            pdf.cell(0, 8, "Score Components:", 0, 1, 'L')
            pdf.set_text_color(0, 0, 0)
            pdf.set_font_for_content('', 10)
            
            pdf.multi_cell(0, 6, f"Pain Score: {breakdown.get('pain_score_adjusted', 0):.1f}/100 (Evidence: {breakdown.get('evidence_count', 0)} sources)")
            pdf.multi_cell(0, 6, f"Market Growth: {breakdown.get('growth_score', 0):.1f}/100 (YoY: {breakdown.get('growth_pct', 0):.1f}%)")
            pdf.multi_cell(0, 6, f"Competition: {breakdown.get('competition_score', 0):.1f}/100 ({breakdown.get('competition_level', 'Unknown')}, {breakdown.get('competitor_count', 0)} found)")
            
            pdf.ln(5)
            
            # Warnings
            warnings = opp_data.get('warnings', [])
            if warnings:
                pdf.set_font_for_content('B', 11)
                pdf.set_text_color(200, 50, 50)
                pdf.cell(0, 8, "⚠ Warnings:", 0, 1, 'L')
                pdf.set_text_color(0, 0, 0)
                pdf.set_font_for_content('', 9)
                
                for warning in warnings:
                    pdf.multi_cell(0, 5, f"• {warning}")
            
        except Exception as e:
            logger.error(f"   ⚠️ Error loading opportunity analysis: {e}")
    
    # --- PAGE 3: MARKET VALIDATION ---
    pdf.add_page()
    logger.info(f"   📄 Generating Page {pdf.page_no()}: Market Validation")
    pdf.chapter_title("Market Validation & Evidence")
    
    val_file = f"data_output/{idea_name.replace(' ', '_')}_validation.json"
    if os.path.exists(val_file):
        try:
            with open(val_file, 'r') as f:
                val_data = json.load(f)
            
            pain_score = val_data.get('pain_score', 0)
            pdf.draw_score_bar("Pain Score (Problem Severity)", pain_score)
            
            # Evidence quality
            evidence_qual = val_data.get('evidence_quality', {})
            pdf.set_font_for_content('B', 11)
            pdf.cell(0, 8, f"Evidence Quality: {evidence_qual.get('quality_level', 'Unknown').title()}", 0, 1, 'L')
            pdf.set_font_for_content('', 10)
            pdf.multi_cell(0, 6, f"Sources analyzed: {evidence_qual.get('total_count', 0)} across {evidence_qual.get('source_diversity', 0)} platforms")
            pdf.multi_cell(0, 6, f"Credibility score: {evidence_qual.get('credibility_score', 0):.2f}/1.0")
            
        except Exception as e:
            logger.error(f"   ⚠️ Error reading validation data: {e}")
    
    if os.path.exists("data_output/market_demand_chart.png"):
        pdf.ln(10)
        pdf.add_image_centered("data_output/market_demand_chart.png")
        pdf.ln(5)
        
        # Read Dynamic Analysis
        trend_text = "The chart above illustrates market demand trends."
        if os.path.exists("data_output/trend_analysis.txt"):
            with open("data_output/trend_analysis.txt", "r") as f:
                trend_text = f.read().strip()
                
        pdf.set_font_for_content('', 10)
        pdf.multi_cell(0, 6, pdf_utils.fix_arabic(trend_text))
    
    # --- PAGE 4: FINANCIALS ---
    pdf.add_page()
    logger.info(f"   📄 Generating Page {pdf.page_no()}: Financials")
    pdf.chapter_title("Financial Feasibility")
    
    if os.path.exists("data_output/finance_summary.csv"):
        pdf.cell(0, 10, "1. Startup Cost Estimates", 0, 1, 'L')
        pdf.add_image_centered("data_output/finance_startup_pie.png")
        pdf.ln(2)
        
        fin_text = "Breakdown of estimated initial capital requirements."
        if os.path.exists("data_output/financial_analysis.txt"):
            with open("data_output/financial_analysis.txt", "r") as f:
                fin_text = f.read().strip()
                
        pdf.set_font_for_content('', 10)
        pdf.multi_cell(0, 6, pdf_utils.fix_arabic(fin_text))
        
        pdf.add_page()
        pdf.chapter_title("Profitability Projections")
        pdf.cell(0, 10, "2. Break-Even Analysis", 0, 1, 'L')
        pdf.add_image_centered("data_output/finance_breakeven_line.png")
    else:
        pdf.set_text_color(255, 0, 0)
        pdf.cell(0, 10, "Financial data unavailable.", 0, 1, 'L')
        pdf.set_text_color(0, 0, 0)

    # --- PAGE 5: MARKET SIZING ---
    pdf.add_page()
    logger.info(f"   📄 Generating Page {pdf.page_no()}: Market Sizing")
    pdf.chapter_title("Market Opportunity & Sizing")
    
    if os.path.exists("data_output/market_sizing.json"):
        with open("data_output/market_sizing.json", "r") as f:
            size_data = json.load(f)
        
        ocean = size_data.get("market_type", "Unknown")
        color = (200, 50, 50) if "Red" in ocean else pdf_utils.PDFReport.COLOR_MOSS
        
        pdf.set_font_for_content('B', 14)
        pdf.set_text_color(*color)
        pdf.cell(0, 10, f"Market Type: {ocean}", 0, 1, 'C')
        pdf.set_text_color(0, 0, 0)
        pdf.ln(5)

        pdf.add_image_centered("data_output/market_sizing_funnel.png")
        
        pdf.set_font_for_content('', 10)
        pdf.multi_cell(0, 6, f"TAM: {size_data.get('tam_description', 'N/A')}")
        pdf.ln(2)
        pdf.multi_cell(0, 6, f"SAM: {size_data.get('sam_description', 'N/A')}")
        pdf.ln(2)
        pdf.multi_cell(0, 6, f"SOM: {size_data.get('som_description', 'N/A')}")
        pdf.ln(5)
        
        pdf.chapter_title("Scalability Analysis")
        pdf.set_font_for_content('B', 12)
        pdf.cell(0, 10, f"Scalability: {size_data.get('scalability_score', 'N/A')}", 0, 1)
        pdf.set_font_for_content('', 11)
        pdf.multi_cell(0, 6, size_data.get('scalability_reasoning', 'N/A'))
    
    # --- PAGE 6: COMPETITORS ---
    pdf.add_page()
    logger.info(f"   📄 Generating Page {pdf.page_no()}: Competitors")
    pdf.chapter_title("Competitor Analysis")
    
    comp_files = glob.glob(f"data_output/{idea_name.replace(' ', '_')}_competitors.csv")
    if comp_files:
        try:
            df = pd.read_csv(comp_files[0])
            
            pdf.set_font_for_content('B', 10)
            pdf.set_fill_color(*pdf_utils.PDFReport.COLOR_MOSS)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(50, 10, 'Competitor', 1, 0, 'C', True)
            pdf.cell(140, 10, 'Key Features', 1, 1, 'C', True)
            pdf.set_text_color(0, 0, 0)
            
            pdf.set_font_for_content('', 9)
            for _, row in df.head(8).iterrows():
                name = pdf_utils.fix_arabic(row.get('Name', 'N/A'))[:25]
                features = pdf_utils.fix_arabic(row.get('Features', 'N/A'))[:110]
                
                pdf.cell(50, 10, name, 1)
                pdf.cell(140, 10, features, 1)
                pdf.ln()
        except Exception as e:
            logger.error(f"   ⚠️ Error adding competitors: {e}")
    
    # --- OUTPUT ---
    clean_name = idea_name.replace(' ', '_').replace('"', '').replace("'", "")
    output_filename = f"data_output/{clean_name}_Market_Report.pdf"
    
    try:
        pdf.output(output_filename)
        logger.info(f"✅ PDF GENERATED: {output_filename}")
        return output_filename
    except Exception as e:
        logger.error(f"❌ PDF Save Failed: {e}")
        return None

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

    # Opportunity Analysis (NEW)
    if os.path.exists("data_output/opportunity_analysis.json"):
        with open("data_output/opportunity_analysis.json", "r") as f:
            json_data["opportunity_analysis"] = json.load(f)

    # Market Sizing
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
