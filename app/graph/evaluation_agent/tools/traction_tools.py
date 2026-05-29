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
from ..prompts.traction_prompts import (
    TRACTION_SCORING_PRE_SEED_PROMPT,
    TRACTION_SCORING_SEED_PROMPT
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

@retry(**RETRY_CONFIG)
async def traction_risk_agent(traction_data: dict, risk_prompt_template: str) -> str:
    async with modal_limiter:
        llm = get_llm(temperature=0, provider="modal")
        chain = PromptTemplate.from_template(risk_prompt_template) | llm | StrOutputParser()
        return await chain.ainvoke({"traction_json": json.dumps(traction_data, indent=2)})
@retry(**RETRY_CONFIG)
async def traction_scoring_agent(data_package: dict) -> dict:
    async with groq_limiter:
        logger.info("🚀 Traction Scoring...")
        llm = get_llm(temperature=0, provider="groq")
        traction_data = data_package.get("traction_data", {})
        stage_raw = traction_data.get("context", {}).get("stage", "Pre-Seed").lower()
        template = TRACTION_SCORING_PRE_SEED_PROMPT if "pre" in stage_raw else TRACTION_SCORING_SEED_PROMPT
        chain = PromptTemplate.from_template(template) | llm | StrOutputParser()
        
        gm = traction_data.get("growth_metrics", {})
        raw_res = await chain.ainvoke({
            "current_date": datetime.now().strftime("%Y-%m-%d"),
            "internal_data": json.dumps(traction_data, indent=2),
            "contradiction_report": str(data_package.get("contradiction_report", "None")),
            "risk_report": str(data_package.get("risk_report", "None")),
            # Pre-extracted key signals so the model cannot hallucinate them as 0/null
            "kv_active_users": str(gm.get("active_users", 0)),
            "kv_growth_rate_mom": str(gm.get("growth_rate_mom", "Not specified")),
            "kv_mrr": str(gm.get("mrr") or "$0"),
            "kv_paid_users": str(gm.get("paid_users", 0)),
            "kv_consumer_note": traction_data.get("context", {}).get("consumer_note", ""),
        })
        
        result_dict = parse_and_repair_json(raw_res)
        result_dict["score_numeric"] = safe_score_numeric(result_dict)
        return result_dict