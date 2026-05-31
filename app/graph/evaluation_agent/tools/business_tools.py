import json
from datetime import datetime


# LangChain & AI Imports
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError
from google.api_core.exceptions import ResourceExhausted
from groq import APIStatusError as GroqAPIStatusError

# Resilience
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Relative Imports
from ..prompts.general_prompts import (
    BUSINESS_MODEL_JUDGE_PROMPT,
    ECONOMIC_JUDGEMENT_PROMPT
)
from ..prompts.business_prompts import (
    SCORING_BIZ_PRE_SEED_PROMPT,
    SCORING_BIZ_SEED_PROMPT
)
from ..helpers import (
    parse_and_repair_json, safe_score_numeric
)
from app.core.llm import get_llm
from app.core.logger import get_logger
from app.core.limiter import groq_limiter, modal_limiter
# Load Environment Variables

# --- INITIALIZE LOGGER ---
logger = get_logger(__name__)

# --- CONFIGURATION ---
RETRY_CONFIG = {
    "wait": wait_exponential(multiplier=2, min=2, max=60),
    "stop": stop_after_attempt(20),
    "retry": retry_if_exception_type((ResourceExhausted, ChatGoogleGenerativeAIError, GroqAPIStatusError))
}

# --- TOOLS & AGENTS ---

def calculate_economics_with_judgment(gtm_data: dict) -> dict:
    logger.info("🧮 Calculating Unit Economics & Business Logic...")

    econ = gtm_data.get("unit_economics", {}) or gtm_data.get("economics_inputs", {})
    context = gtm_data.get("context", {})
    strategy = gtm_data.get("strategy", {})
    
    # IMPROVED: Handle placeholder strings like "string"
    def safe_float(val):
        try: 
            if isinstance(val, (int, float)): return float(val)
            clean_val = str(val).replace('$', '').replace(',', '').strip()
            return float(clean_val)
        except (ValueError, TypeError): 
            return 0.0

    burn = safe_float(econ.get("burn_rate"))
    total_users = safe_float(econ.get("total_users"))
    paid_users = safe_float(econ.get("paid_users"))
    revenue = safe_float(econ.get("revenue") or econ.get("early_revenue"))
    price = safe_float(econ.get("price_point"))
    
    # Calculate months_alive ONLY ONCE - do not hardcode 6 later
    founded_str = context.get("founded_date")
    try:
        f_date = datetime.strptime(founded_str, "%Y-%m-%d") if founded_str else datetime.now()
        months_alive = max((datetime.now() - f_date).days / 30, 1)
    except:
        months_alive = 6
    
    avg_new_users_mo = total_users / months_alive if months_alive > 0 else 0

    metrics = {
        "monthly_burn": f"${int(burn)}",
        "price_point": f"${int(price)}",
        "revenue": f"${int(revenue)}"
    }

    # CAC Calculation using the actual variables
    est_s_m_spend = burn * 0.30
    
    # Use 0.0 instead of "N/A" to keep types consistent
    if avg_new_users_mo > 0: 
        metrics["implied_cac"] = round(est_s_m_spend / avg_new_users_mo, 2)
    else: 
        metrics["implied_cac"] = 0.0
    
    metrics["conversion_rate"] = round((paid_users / total_users) * 100, 2) if total_users > 0 else 0.0

    # SAFE comparison: price is guaranteed to be float by safe_float
    if price > 0 and metrics["implied_cac"] > 0:
        metrics["payback_months"] = round(metrics["implied_cac"] / price, 1)
    else: 
        metrics["payback_months"] = 0.0

    # AI JUDGE
    try:
        llm = get_llm(temperature=0, provider="groq")
        chain = PromptTemplate.from_template(ECONOMIC_JUDGEMENT_PROMPT) | llm | StrOutputParser()
        raw_judge = chain.invoke({
            "sector_info": strategy.get("icp_description", "Tech"),
            "stage": context.get("stage", "Pre-Seed"),
            "model": strategy.get("pricing_model", "Unknown"),
            "cac": metrics["implied_cac"],
            "price": price,
            "payback": metrics["payback_months"],
            "conversion": metrics["conversion_rate"],
            "burn": metrics["monthly_burn"],
            "revenue": metrics["revenue"],
            "paid_users": int(paid_users),
            "users": int(total_users)
        })
        metrics["ai_analysis"] = parse_and_repair_json(raw_judge)
    except Exception as e:
        logger.error(f"AI Judgment Failed: {e}") # This will catch your 401 error
        metrics["ai_analysis"] = {"error": "AI Service Unavailable - Check API Key"}

    return metrics
async def evaluate_business_model_with_context(business_data: dict) -> dict:
    async with groq_limiter:
        logger.info("💰 Analyzing Business Model & Economics...")
        structure = business_data.get("monetization_structure", {})
        cash = business_data.get("cash_health", {})
        context = business_data.get("context", {})
        
        # ... (Extraction logic) ...
        def safe_float(val):
            try: return float(val)
            except: return 0.0
            
        price = safe_float(structure.get("price_point"))
        margin_percent = safe_float(structure.get("gross_margin"))
        burn = safe_float(cash.get("burn_rate"))
        runway_stated = safe_float(cash.get("runway_months"))
        cost_to_serve = price * (1 - (margin_percent / 100)) if price > 0 else 0

        # LLM Judge
        llm = get_llm(temperature=0, provider="groq")
        chain = PromptTemplate.from_template(BUSINESS_MODEL_JUDGE_PROMPT) | llm | StrOutputParser()
        
        try:
            raw_res = await chain.ainvoke({
                "company_name": context.get("company_name", "Startup"),
                "stage": context.get("stage", "Pre-Seed"),
                "sector_info": business_data.get("sector_context", "Tech"),
                "pricing_model": structure.get("pricing_model", "Unknown"),
                "price": price,
                "margin": margin_percent,
                "burn": int(burn),
                "runway": runway_stated,
                "growth": "0%",
                "cost_to_serve": round(cost_to_serve, 2)
            })
            ai_verdict = parse_and_repair_json(raw_res)
            
            return {
                "metrics": {
                    "monthly_burn": f"${int(burn)}",
                    "runway_months": runway_stated,
                    "gross_margin": f"{margin_percent}%"
                },
                "ai_analysis": ai_verdict
            }
        except Exception as e:
            return {"error": str(e)}
@retry(**RETRY_CONFIG)
async def business_risk_agent(business_data: dict, risk_prompt_template: str) -> str:
    async with modal_limiter:
        llm = get_llm(temperature=0, provider="modal")
        chain = PromptTemplate.from_template(risk_prompt_template) | llm | StrOutputParser()
        return await chain.ainvoke({"business_data": json.dumps(business_data, indent=2)})
@retry(**RETRY_CONFIG)
async def business_scoring_agent(data_package: dict) -> dict:
    async with groq_limiter:
        logger.info("🚀 Business Scoring...")
        llm = get_llm(temperature=0, provider="groq")
        business_data = data_package.get("business_data", {})
        stage_raw = business_data.get("context", {}).get("stage", "Pre-Seed").lower()
        template = SCORING_BIZ_PRE_SEED_PROMPT if "pre" in stage_raw else SCORING_BIZ_SEED_PROMPT
        chain = PromptTemplate.from_template(template) | llm | StrOutputParser()
        
        ms = business_data.get("monetization_structure", {})
        rm = business_data.get("revenue_momentum", {})
        ch = business_data.get("cash_health", {})
        raw_res = await chain.ainvoke({
            "current_date": datetime.now().strftime("%Y-%m-%d"),
            "business_data": json.dumps(business_data, indent=2),
            "calculator_report": json.dumps(data_package.get("calculator_report", {}), indent=2),
            "contradiction_report": str(data_package.get("contradiction_report", "None")),
            "risk_report": str(data_package.get("risk_report", "None")),
            # Pre-extracted to prevent hallucination of 0/null for these critical fields
            "kv_gross_margin": str(ms.get("gross_margin") or "Not specified"),
            "kv_pricing_model": str(ms.get("pricing_model") or "Not specified"),
            "kv_mrr": str(rm.get("mrr") or "$0"),
            "kv_growth_rate": str(rm.get("growth_rate") or "Not specified"),
            "kv_active_users": str(rm.get("active_users", 0)),
            "kv_burn_rate": str(ch.get("burn_rate") or "Not specified"),
            "kv_runway": str(ch.get("runway_months") or "Not specified"),
        })
        
        result_dict = parse_and_repair_json(raw_res)
        result_dict["score_numeric"] = safe_score_numeric(result_dict)
        return result_dict