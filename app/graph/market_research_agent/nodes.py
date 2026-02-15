from app.graph.market_research_agent.state import MarketResearchState
from .tools import (
    find_competitors,
    validate_problem,
    fetch_trend_data,
    run_finance_model,
    generate_report,
    compile_final_pdf,
    compile_final_json,
    calculate_market_size
)
import os
from app.core.logger import get_logger

from app.graph.market_research_agent.helpers.research_utils import generate_research_plan, execute_serper_search, extract_competitors_strict

logger = get_logger("MarketResearchNodes")

def plan_node(state: MarketResearchState):
    logger.info("\n👉 Step 0: Developing Research Strategy (Consolidated Gemini Call)...")
    idea = state.get("input_idea")
    problem = state.get("input_problem")
    
    # ONE Call to Rule Them All
    plan = generate_research_plan(idea, problem)
    return {"research_plan": plan}

def competitors_node(state: MarketResearchState):
    logger.info("\n👉 Step 1: Researching Competitors (Using Plan)...")
    idea = state.get("input_idea")
    plan = state.get("research_plan")
    
    if not plan:
        logger.warning("Research plan missing. Skipping competitors search.")
        return {"competitors_file": None}
    
    # Use pre-generated queries
    queries = plan.get("competitor_queries", [f"{idea} alternatives"])
    
    # Execute Search (1-2 calls max due to previous optimization)
    search_data = execute_serper_search(queries)
    
    # Extract Competitors (using filtered results)
    competitors_list = extract_competitors_strict(search_data, idea)
        
    from .tools import find_competitors_from_plan
    file_path = find_competitors_from_plan(idea, plan)
    return {"competitors_file": file_path}

def validation_node(state: MarketResearchState):
    logger.info("\n👉 Step 2: Validating Pain Points...")
    idea = state.get("input_idea")
    problem = state.get("input_problem")
    plan = state.get("research_plan")
    
    file_path = validate_problem(idea, problem, plan=plan)
    return {"validation_file": file_path}

def trends_node(state: MarketResearchState):
    logger.info("\n👉 Step 3: Analyzing Market Trends...")
    idea = state.get("input_idea")
    plan = state.get("research_plan")
    
    trend_keyword = idea.split(" in ")[0] # Fallback
    if plan: 
        industry = plan.get("market_identity", {}).get("industry")
        if industry: trend_keyword = industry
    
    trend_csv, _ = fetch_trend_data([trend_keyword], geo_code='EG', plan=plan)
    return {"trends_file": trend_csv}

def finance_node(state: MarketResearchState):
    logger.info("\n👉 Step 5: Building Financial Model...")
    idea = state.get("input_idea")
    plan = state.get("research_plan")
    
    finance_csv = run_finance_model(idea, plan=plan)
    return {"finance_file": finance_csv}

def market_sizing_node(state: MarketResearchState):
    logger.info("\n👉 Step 6: Calculating TAM/SAM/SOM...")
    idea = state.get("input_idea")
    plan = state.get("research_plan")
    
    location = "Global"
    if plan:
        location = plan.get("market_identity", {}).get("target_country", "Global")
        
    file_path = calculate_market_size(idea, location=location, plan=plan)
    return {"market_limit_file": file_path}

def report_node(state: MarketResearchState):
    logger.info("\n👉 Step 7: Writing Strategy Report...")
    idea = state.get("input_idea")
    val_file = state.get("validation_file")
    trend_file = state.get("trends_file")
    finance_file = state.get("finance_file")
    
    # Always attempt to generate report, even if some inputs are missing
    logger.info(f"Generating report for: {idea}")
    generate_report(val_file if val_file else "", idea, trend_file=trend_file, finance_file=finance_file)
        
    return {"report_text": "Report Generated"}

def pdf_node(state: MarketResearchState):
    logger.info("\n👉 Step 8: Compiling Final PDF & JSON Deck...")
    idea = state.get("input_idea")
    pdf_file = compile_final_pdf(idea)
    json_file = compile_final_json(idea)
    
    result = f"Research complete.\nPDF Report: {pdf_file}\nJSON Data: {json_file}"
    return {"pdf_path": pdf_file, "json_path": json_file, "market_research": result}
