import asyncio
import json
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from app.core.llm import get_llm
from .state import AgentState
from .tools import (
    contradiction_check, 
    team_risk_check, 
    team_scoring_agent,
    verify_problem_claims, 
    loaded_risk_check_with_search, 
    problem_scoring_agent,
    tech_stack_detective, 
    analyze_visuals_with_langchain, 
    product_scoring_agent,
    tam_sam_verifier_tool,
    regulation_trend_radar_tool,
    local_dependency_detective,
    market_scoring_agent,
    traction_risk_agent,
    traction_scoring_agent,
    gtm_risk_agent,
    gtm_scoring_agent,
    calculate_economics_with_judgment,
    business_risk_agent,
    evaluate_business_model_with_context,
    business_scoring_agent,
    analyze_category_future,
    vision_risk_agent,
    vision_scoring_agent,
    get_funding_benchmarks,
    operations_risk_agent,
    operations_scoring_agent
)
from .prompts import (
    PLANNER_PROMPT,
    CONTRADICTION_TEAM_PROMPT_TEMPLATE,
    VALUATION_RISK_TEAM_PROMPT_TEMPLATE,
    CONTRADICTION_PROBLEM_PROMPT_TEMPLATE,
    VALUATION_RISK_PROBLEM_PROMPT_TEMPLATE,
    CONTRADICTION_PRODUCT_PROMPT_TEMPLATE, 
    VALUATION_RISK_PRODUCT_PROMPT_TEMPLATE,
    VISUAL_VERIFICATION_PROMPT,
    CONTRADICTION_MARKET_PROMPT_TEMPLATE,
    CONTRADICTION_PRE_SEED_TRACTION_AGENT_PROMPT,
    CONTRADICTION_SEED_TRACTION_AGENT_PROMPT,
    VALUATION_RISK_TRACTION_PRE_SEED_PROMPT,
    VALUATION_RISK_TRACTION_SEED_PROMPT,
    CONTRADICTION_PRE_SEED_GTM_AGENT_PROMPT,
    CONTRADICTION_SEED_GTM_AGENT_PROMPT,
    VALUATION_RISK_GTM_PRE_SEED_PROMPT,
    VALUATION_RISK_GTM_SEED_PROMPT,
    CONTRADICTION_PRE_SEED_BIZ_MODEL_PROMPT,
    CONTRADICTION_SEED_BIZ_MODEL_PROMPT,
    RISK_BIZ_MODEL_PRE_SEED_PROMPT,
    RISK_BIZ_MODEL_SEED_PROMPT,
    CONTRADICTION_VISION_PROMPT_TEMPLATE,
    VALUATION_RISK_VISION_PRE_SEED_PROMPT,
    VALUATION_RISK_VISION_SEED_PROMPT,
    CONTRADICTION_OPERATIONS_PROMPT_TEMPLATE,
    VALUATION_RISK_OPS_PRE_SEED_PROMPT,
    VALUATION_RISK_OPS_SEED_PROMPT,
    FINAL_SYNTHESIS_PROMPT
)
from .helpers import (
    extract_team_data, 
    extract_problem_data, 
    extract_product_data, 
    check_missing_fields,
    extract_market_data,
    extract_traction_data,
    extract_gtm_pre_seed,
    extract_gtm_seed,
    extract_business_pre_seed,
    extract_business_seed,
    extract_vision_data,
    extract_operations_data
)
from .schema import Plan
from langchain_google_genai import ChatGoogleGenerativeAI
import os
from app.core.logger import get_logger
from app.core.llm import get_llm
logger = get_logger(__name__)

async def planner_node(state: AgentState):
    """
    Generates a strategic plan for the evaluation based on initial user data.
    """
    user_data = state.get("user_data", {})
    
    llm = get_llm(temperature=0, provider="groq")
    
    # Structured output binding
    structured_llm = llm.with_structured_output(Plan)
    
    try:
        plan_obj = await structured_llm.ainvoke(
            PLANNER_PROMPT.format(user_data=json.dumps(user_data, indent=2))
        )
        return {"plan": plan_obj.model_dump()}
    except Exception as e:
        # Fallback empty plan if fails
        return {"plan": {"steps": [], "key_risks": ["Planning Failed"], "desired_output_structure": []}}

async def team_node(state: AgentState):
    """
    Parallel Execution of Team Contradiction & Risk Checks, followed by Scoring.
    """
    user_data = state.get("user_data", {})
    team_data = extract_team_data(user_data)
    missing_report = check_missing_fields(user_data) 

    # Parallel Execution
    contradiction_task = contradiction_check(team_data, CONTRADICTION_TEAM_PROMPT_TEMPLATE)
    risk_task = team_risk_check(team_data, VALUATION_RISK_TEAM_PROMPT_TEMPLATE)
    
    contradiction_res, risk_res = await asyncio.gather(contradiction_task, risk_task)
    
    # Scoring
    package = {
        "user_data": team_data,
        "risk_report": risk_res,
        "contradiction_report": contradiction_res,
        "missing_report": missing_report
    }
    score = await team_scoring_agent(package)
    
    return {"team_report": score}

async def problem_node(state: AgentState):
    """
    Parallel Execution of Search & Contradiction, followed by Risk, then Scoring.
    """
    user_data = state.get("user_data", {})
    problem_data = extract_problem_data(user_data)
    problem_def = user_data.get("startup_evaluation", {}).get("problem_definition", {})
    missing_report = check_missing_fields(user_data)

    # 1. Parallel: Search & Contradiction
    search_task = verify_problem_claims(
        problem_statement=problem_def.get("problem_statement", ""),
        target_audience=problem_def.get("customer_profile", {}).get("role", "")
    )
    contradiction_task = contradiction_check(problem_data, CONTRADICTION_PROBLEM_PROMPT_TEMPLATE)

    search_res, contradiction_res = await asyncio.gather(search_task, contradiction_task)

    # 2. Risk Check (Needs Search Results)
    risk_res = await loaded_risk_check_with_search(
        problem_data=problem_def,
        search_results=search_res,
        agent_prompt=VALUATION_RISK_PROBLEM_PROMPT_TEMPLATE
    )

    # 3. Scoring
    package = {
        "problem_definition": problem_def,
        "missing_report": missing_report,
        "search_report": search_res,
        "risk_report": risk_res,
        "contradiction_report": contradiction_res
    }
    score = await problem_scoring_agent(package)

    return {
        "problem_report": score,
        "search_results": search_res,
        "risk_report": risk_res,
        "contradiction_report": contradiction_res
    }

async def product_tools_node(state: AgentState):
    """
    Parallel Branch 1: Heavy Tools (Tech Stack & Visuals)
    """
    user_data = state.get("user_data", {})
    url = user_data.get("startup_evaluation", {}).get("company_snapshot", {}).get("website_url", "")
    company = user_data.get("startup_evaluation", {}).get("company_snapshot", {}).get("company_name", "Startup")
    
    # Run heavy IO tasks
    tech_res, visual_res = await asyncio.gather(
        tech_stack_detective(url),
        analyze_visuals_with_langchain(company, url, VISUAL_VERIFICATION_PROMPT)
    )
    
    return {
        "tech_stack": tech_res, 
        "visual_analysis": visual_res
    }

async def product_contradiction_node(state: AgentState):
    """
    Parallel Branch 2: Logic Check
    """
    user_data = state.get("user_data", {})
    product_data = extract_product_data(user_data)
    
    res = await contradiction_check(product_data, CONTRADICTION_PRODUCT_PROMPT_TEMPLATE)
    return {"product_contradiction": res}

async def product_risk_node(state: AgentState):
    """
    Parallel Branch 3: Market Risk & Competitor Check
    """
    user_data = state.get("user_data", {})
    problem_def = user_data.get("startup_evaluation", {}).get("problem_definition", {})
    
    # We need competitor search results. If not in state, do a quick check.
    # Ideally, we reuse 'search_results' from problem_node if it finished, 
    # but since they run in parallel, we do a targeted micro-search here to be safe/fast.
    search_res = await verify_problem_claims(
        problem_def.get("problem_statement", ""), 
        problem_def.get("customer_profile", {}).get("role", "")
    )
    
    risk_res = await loaded_risk_check_with_search(
        problem_data=extract_product_data(user_data), 
        search_results=search_res.get("competitor_search", []),
        agent_prompt=VALUATION_RISK_PRODUCT_PROMPT_TEMPLATE
    )
    
    return {"product_risk_report": risk_res}

async def product_final_scoring_node(state: AgentState):
    """
    Convergence Point: Aggregates everything for the final score.
    """
    user_data = state.get("user_data", {})
    
    score = await product_scoring_agent({
        "internal_data": extract_product_data(user_data),
        "contradiction_report": state.get("product_contradiction", "None"),
        "risk_report": state.get("product_risk_report", "None"),
        "tech_stack_report": state.get("tech_stack", "None"),
        "visual_analysis_report": state.get("visual_analysis", "None")
    })
    
    return {"product_report": score}

async def planner_node(state: AgentState):
    """Generates a strategic plan."""
    user_data = state.get("user_data", {})
    llm = get_llm(temperature=0, provider="groq")  
    structured_llm = llm.with_structured_output(Plan)
    
    try:
        plan_obj = await structured_llm.ainvoke(
            PLANNER_PROMPT.format(user_data=json.dumps(user_data, indent=2))
        )
        return {"plan": plan_obj.model_dump()}
    except Exception:
        return {"plan": {"steps": [], "key_risks": ["Planning Failed"], "desired_output_structure": []}}

async def team_node(state: AgentState):
    """Team Evaluation."""
    user_data = state.get("user_data", {})
    team_data = extract_team_data(user_data)
    missing_report = check_missing_fields(user_data) 

    contradiction_res, risk_res = await asyncio.gather(
        contradiction_check(team_data, CONTRADICTION_TEAM_PROMPT_TEMPLATE),
        team_risk_check(team_data, VALUATION_RISK_TEAM_PROMPT_TEMPLATE)
    )
    
    score = await team_scoring_agent({
        "user_data": team_data, "risk_report": risk_res,
        "contradiction_report": contradiction_res, "missing_report": missing_report
    })
   
    return {"team_report": score}

async def problem_node(state: AgentState):
    """Problem Evaluation."""
    user_data = state.get("user_data", {})
    problem_data = extract_problem_data(user_data)
    problem_def = user_data.get("startup_evaluation", {}).get("problem_definition", {})
    missing_report = check_missing_fields(user_data)

    search_res, contradiction_res = await asyncio.gather(
        verify_problem_claims(problem_def.get("problem_statement", ""), problem_def.get("customer_profile", {}).get("role", "")),
        contradiction_check(problem_data, CONTRADICTION_PROBLEM_PROMPT_TEMPLATE)
    )

    risk_res = await loaded_risk_check_with_search(
        problem_data=problem_def, search_results=search_res,
        agent_prompt=VALUATION_RISK_PROBLEM_PROMPT_TEMPLATE
    )

    score = await problem_scoring_agent({
        "problem_definition": problem_def, "missing_report": missing_report,
        "search_report": search_res, "risk_report": risk_res,
        "contradiction_report": contradiction_res
    })
    return {"problem_report": score, "search_results": search_res, "problem_risk_report": risk_res}

async def product_tools_node(state: AgentState):
    """Product Tools (Heavy I/O)."""
    user_data = state.get("user_data", {})
    url = user_data.get("startup_evaluation", {}).get("company_snapshot", {}).get("website_url", "")
    company = user_data.get("startup_evaluation", {}).get("company_snapshot", {}).get("company_name", "Startup")
    product_data = extract_product_data(user_data)

    tech_res, visual_res, contradiction_res = await asyncio.gather(
        tech_stack_detective(url),
        analyze_visuals_with_langchain(company, url, VISUAL_VERIFICATION_PROMPT),
        contradiction_check(product_data, CONTRADICTION_PRODUCT_PROMPT_TEMPLATE)
    )
    return {"tech_stack": tech_res, "visual_analysis": visual_res, "product_contradiction": contradiction_res}

async def product_scoring_node(state: AgentState):
    """Product Scoring."""
    user_data = state.get("user_data", {})
    search_res = state.get("search_results")
    if not search_res:
        problem_def = user_data.get("startup_evaluation", {}).get("problem_definition", {})
        search_res = await verify_problem_claims(problem_def.get("problem_statement", ""), problem_def.get("customer_profile", {}).get("role", ""))
    
    risk_res = await loaded_risk_check_with_search(
        problem_data=extract_product_data(user_data), 
        search_results=search_res.get("competitor_search", []),
        agent_prompt=VALUATION_RISK_PRODUCT_PROMPT_TEMPLATE
    )

    score = await product_scoring_agent({
        "internal_data": extract_product_data(user_data),
        "contradiction_report": state.get("product_contradiction", "None"),
        "risk_report": risk_res,
        "tech_stack_report": state.get("tech_stack"),
        "visual_analysis_report": state.get("visual_analysis")
    })
    return {"product_report": score, "product_risk_report": risk_res}

# =========================================================
# NEW NODES (Market, Traction, GTM, Biz, Vision, Ops)
# =========================================================

async def market_node(state: AgentState):
    """Market Analysis Node."""
    user_data = state.get("user_data", {})
    market_data = extract_market_data(user_data)
    
    # 1. Parallel: TAM, Radar, Contradiction
    tam_task = tam_sam_verifier_tool(
        market_data["entry_point"]["beachhead_definition"],
        market_data["entry_point"]["location"],
        market_data["entry_point"]["som_size_claim"]
    )
    radar_task = regulation_trend_radar_tool(
        market_data["scalability"]["future_category"],
        market_data["entry_point"]["location"]
    )
    con_task = contradiction_check(market_data, CONTRADICTION_MARKET_PROMPT_TEMPLATE)
    
    tam_res, radar_res, con_res = await asyncio.gather(tam_task, radar_task, con_task)
    
    # 2. Dependency Check (Needs some context)
    dep_res = await local_dependency_detective(
        tech_stack=f"{market_data['scalability']['future_category']}",
        acquisition_channel=market_data['risks']['acquisition_channel'],
        product_desc=market_data['scalability']['future_category']
    )
    
    # 3. Score
    score = await market_scoring_agent({
        "internal_data": market_data,
        "contradiction_report": con_res,
        "tam_report": tam_res,
        "radar_report": radar_res,
        "dependency_report": dep_res
    })
    
    return {"market_report": score}

async def traction_node(state: AgentState):
    """Traction Analysis Node."""
    user_data = state.get("user_data", {})
    traction_data = extract_traction_data(user_data)
    stage = traction_data["context"]["stage"].lower()
    
    # Select Prompts
    risk_prompt = VALUATION_RISK_TRACTION_PRE_SEED_PROMPT if "pre" in stage else VALUATION_RISK_TRACTION_SEED_PROMPT
    con_prompt = CONTRADICTION_PRE_SEED_TRACTION_AGENT_PROMPT if "pre" in stage else CONTRADICTION_SEED_TRACTION_AGENT_PROMPT
    
    # Parallel Checks
    risk_res, con_res = await asyncio.gather(
        traction_risk_agent(traction_data, risk_prompt),
        contradiction_check(traction_data, con_prompt)
    )
    
    score = await traction_scoring_agent({
        "traction_data": traction_data,
        "contradiction_report": con_res,
        "risk_report": risk_res
    })
    return {"traction_report": score}

async def gtm_node(state: AgentState):
    """GTM Strategy Node."""
    user_data = state.get("user_data", {})
    
    # Extract based on stage
    stage_raw = user_data.get("startup_evaluation", {}).get("company_snapshot", {}).get("current_stage", "Pre-Seed").lower()
    if "pre" in stage_raw:
        gtm_data = extract_gtm_pre_seed(user_data)
        risk_prompt = VALUATION_RISK_GTM_PRE_SEED_PROMPT
        con_prompt = CONTRADICTION_PRE_SEED_GTM_AGENT_PROMPT
    else:
        gtm_data = extract_gtm_seed(user_data)
        risk_prompt = VALUATION_RISK_GTM_SEED_PROMPT
        con_prompt = CONTRADICTION_SEED_GTM_AGENT_PROMPT
    
    # Run Calc locally for GTM context
    economics = calculate_economics_with_judgment(gtm_data) # This is now imported from tools
    
    risk_res, con_res = await asyncio.gather(
        gtm_risk_agent(gtm_data, risk_prompt),
        contradiction_check(gtm_data, con_prompt)
    )
    
    score = await gtm_scoring_agent(gtm_data, economics, con_res, risk_res)
    return {"gtm_report": score}

async def business_node(state: AgentState):
    """Business Model Node."""
    user_data = state.get("user_data", {})
    
    stage_raw = user_data.get("startup_evaluation", {}).get("company_snapshot", {}).get("current_stage", "Pre-Seed").lower()
    if "pre" in stage_raw:
        biz_data = extract_business_pre_seed(user_data)
        risk_prompt = RISK_BIZ_MODEL_PRE_SEED_PROMPT
        con_prompt = CONTRADICTION_PRE_SEED_BIZ_MODEL_PROMPT
    else:
        biz_data = extract_business_seed(user_data)
        risk_prompt = RISK_BIZ_MODEL_SEED_PROMPT
        con_prompt = CONTRADICTION_SEED_BIZ_MODEL_PROMPT
        
    # Math Calc
    calculator = await evaluate_business_model_with_context(biz_data) # Reuse tool logic

    
    risk_res, con_res = await asyncio.gather(
        business_risk_agent(biz_data, risk_prompt),
        contradiction_check(biz_data, con_prompt)
    )
    
    score = await business_scoring_agent({
        "business_data": biz_data,
        "calculator_report": calculator,
        "contradiction_report": con_res,
        "risk_report": risk_res
    })
    return {"business_report": score}

async def vision_node(state: AgentState):
    """Vision & Narrative Node."""
    user_data = state.get("user_data", {})
    vision_data = extract_vision_data(user_data)
    stage = vision_data["context"]["stage"].lower()
    
    risk_prompt = VALUATION_RISK_VISION_PRE_SEED_PROMPT if "pre" in stage else VALUATION_RISK_VISION_SEED_PROMPT
    
    # Parallel: Market Signal Search & Contradiction
    market_analysis, con_res = await asyncio.gather(
        analyze_category_future(vision_data),
        contradiction_check(vision_data, CONTRADICTION_VISION_PROMPT_TEMPLATE)
    )
    
    # Dependent: Risk needs market analysis output
    risk_res = await vision_risk_agent(vision_data, market_analysis, risk_prompt)
    
    score = await vision_scoring_agent({
        "vision_data": vision_data,
        "market_analysis": market_analysis,
        "contradiction_report": con_res,
        "risk_report": risk_res
    })
    return {"vision_report": score}

async def operations_node(state: AgentState):
    """Operations & Fundability Node."""
    user_data = state.get("user_data", {})
    ops_data = extract_operations_data(user_data)
    stage = ops_data["context"]["stage"].lower()
    
    risk_prompt = VALUATION_RISK_OPS_PRE_SEED_PROMPT if "pre" in stage else VALUATION_RISK_OPS_SEED_PROMPT
    
    # Parallel: Benchmarks & Contradiction
    benchmarks, con_res = await asyncio.gather(
        get_funding_benchmarks(ops_data["context"]["location"], ops_data["context"]["stage"], ops_data["context"]["sector"]),
        contradiction_check(ops_data, CONTRADICTION_OPERATIONS_PROMPT_TEMPLATE)
    )
    
    risk_res = await operations_risk_agent(ops_data, benchmarks, risk_prompt)
    
    score = await operations_scoring_agent({
        "operations_data": ops_data,
        "benchmarks": benchmarks,
        "contradiction_report": con_res,
        "risk_report": risk_res
    })
    return {"operations_report": score}


def calculate_weighted_score(scores: dict, stage: str) -> tuple[float, float, str, dict]:
    # 1. Normalize 0-100 to 0-5
    rubric = {k: (v / 20.0) for k, v in scores.items()}
    
    # 2. Apply Stage Weights
    if "pre" in stage.lower():
        weights = {"team": 1.5, "problem": 1.3, "product": 1.2, "market": 1.0, "traction": 1.0, "gtm": 1.0, "business": 1.0, "vision": 1.0, "operations": 1.0}
    else:
        weights = {"team": 1.0, "problem": 1.0, "product": 1.0, "market": 1.0, "traction": 1.5, "gtm": 1.3, "business": 1.2, "vision": 1.0, "operations": 1.0}

    weighted_total = sum(rubric.get(k, 0) * weights.get(k, 1.0) for k in rubric)
    
    # 3. STRICT RUBRIC
    if weighted_total < 20: verdict = "Pass (Not Ready)"
    elif weighted_total < 26: verdict = "High Risk / Optionality"
    elif weighted_total < 33: verdict = "Invest (Team Conviction)"
    elif weighted_total < 40: verdict = "Strong Invest"
    else: verdict = "Extremely Good"

    return 0, weighted_total, verdict, rubric

# --- MAIN NODE ---
async def final_node(state: AgentState):
    user_data = state.get("user_data", {})
    stage = user_data.get("startup_evaluation", {}).get("company_snapshot", {}).get("current_stage", "Pre-Seed")

    # 1. Collect Scores
    raw_scores = {
        k: state.get(f"{k}_report", {}).get("score_numeric", 0) 
        for k in ["team", "problem", "product", "market", "traction", "gtm", "business", "vision", "operations"]
    }

    # 2. Math & Verdict
    _, weighted_total, verdict, rubric_5 = calculate_weighted_score(raw_scores, stage)

    # 3. Build Evidence
    agent_summaries = ""
    for key in raw_scores.keys():
        report = state.get(f"{key}_report", {})
        score_val = rubric_5.get(key, 0)
        explanation = report.get("explanation", "No data")
        confidence = report.get("confidence_level", "Medium")
        greens = [g.replace("Strength 1:", "").strip() for g in report.get("green_flags", [])]
        reds = [r.replace("Risk 1:", "").strip() for r in report.get("red_flags", [])]
        
        agent_summaries += f"""
        === {key.upper()} (Score: {score_val:.1f}/5) ===
        CONFIDENCE: {confidence}
        ANALYSIS: {explanation}
        STRENGTHS: {json.dumps(greens)}
        RISKS: {json.dumps(reds)}
        ------------------------------------------------
        """

    # 4. Generate with LLM
    llm = get_llm(temperature=0, provider="groq") 
    chain = PromptTemplate.from_template(FINAL_SYNTHESIS_PROMPT) | llm | JsonOutputParser()

    try:
        final_json = await chain.ainvoke({
            "stage": stage,
            "scores_summary": json.dumps(rubric_5, indent=2),
            "weighted_score": f"{weighted_total:.1f}",
            "verdict_band": verdict,
            "agent_summaries": agent_summaries
        })
        
        # ====================================================
        # 🛡️ SAFETY BACKFILL (Fixes "Missing Sections")
        # ====================================================
        required_dims = ["team", "problem", "product", "market", "traction", "gtm", "business", "vision", "operations"]
        
        # Access Founder Output safely
        founder_root = final_json.get("founder_output", {})
        founder_content = founder_root.get("Content", founder_root) # Handle nesting
        
        llm_dims = founder_content.get("dimension_analysis", [])
        
        # Map existing dimensions
        llm_map = {}
        if isinstance(llm_dims, list):
            for d in llm_dims:
                name = d.get("dimension", "").lower()
                llm_map[name] = d
        elif isinstance(llm_dims, dict):
            llm_map = {k.lower(): v for k,v in llm_dims.items()}

        # Rebuild complete list
        complete_dims = []
        for key in required_dims:
            if key in llm_map:
                complete_dims.append(llm_map[key])
            else:
                logger.warning(f"Finalizer skipped {key}. Backfilling.")
                raw_report = state.get(f"{key}_report", {})
                complete_dims.append({
                    "dimension": key.title(),
                    "score": rubric_5.get(key, 0),
                    "confidence_level": raw_report.get("confidence_level", "Medium"),
                    "justification": raw_report.get("explanation", "Analysis pending."),
                    "red_flags": raw_report.get("red_flags", []),
                    "improvements": ["Review risks highlighted in analysis."]
                })

        # Save backfill
        if "Content" in final_json.get("founder_output", {}):
            final_json["founder_output"]["Content"]["Dimension Analysis"] = complete_dims
        else:
            final_json["founder_output"]["dimension_analysis"] = complete_dims
        
        # ====================================================
        # 🔢 SCORE OVERWRITE (Fixes "Pending / 0.0" Verdict)
        # ====================================================
        
        # 1. Overwrite INVESTOR Output
        if "Content" in final_json["investor_output"]:
            final_json["investor_output"]["Content"]["Scorecard Grid"] = rubric_5
            final_json["investor_output"]["Content"]["Weighted Score"] = weighted_total
            final_json["investor_output"]["Content"]["Verdict"] = verdict
        else:
            final_json["investor_output"]["scorecard_grid"] = rubric_5
            final_json["investor_output"]["weighted_score"] = weighted_total
            final_json["investor_output"]["verdict"] = verdict

        # 2. Overwrite FOUNDER Output (THIS WAS MISSING BEFORE)
        if "Content" in final_json["founder_output"]:
            final_json["founder_output"]["Content"]["Scorecard Grid"] = rubric_5
            final_json["founder_output"]["Content"]["Weighted Score"] = weighted_total # Fix
            final_json["founder_output"]["Content"]["Verdict"] = verdict             # Fix
        else:
            final_json["founder_output"]["scorecard_grid"] = rubric_5
            final_json["founder_output"]["weighted_score"] = weighted_total          # Fix
            final_json["founder_output"]["verdict"] = verdict                      # Fix

    except Exception as e:
        logger.error(f"Final Synthesis Failed: {e}")
        final_json = {
            "error": str(e),
            "investor_output": {"verdict": verdict, "weighted_score": weighted_total, "scorecard_grid": rubric_5},
            "founder_output": {"verdict": verdict, "score": weighted_total, "scorecard_grid": rubric_5, "dimension_analysis": []}
        }

    return {"final_report": final_json}
