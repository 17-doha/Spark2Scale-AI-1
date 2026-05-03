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
from ..prompts.gtm_prompts import (
    SCORING_GTM_PRE_SEED_PROMPT,
    SCORING_GTM_SEED_PROMPT
)
from ..helpers import (
    parse_and_repair_json, safe_score_numeric
)
from app.core.llm import get_llm
from app.core.logger import get_logger
from app.core.limiter import concurrency_limiter
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
async def gtm_risk_agent(gtm_data: dict, risk_prompt_template: str) -> str:
    async with concurrency_limiter:
        llm = get_llm(temperature=0, provider="modal")
        chain = PromptTemplate.from_template(risk_prompt_template) | llm | StrOutputParser()
        return await chain.ainvoke({"gtm_json": json.dumps(gtm_data, indent=2)})
@retry(**RETRY_CONFIG)
async def gtm_scoring_agent(gtm_data: dict, economics_report: dict, contradiction_report: str, risk_report: str) -> dict:
    async with concurrency_limiter:
        logger.info("🚀 GTM Scoring...")
        llm = get_llm(temperature=0, provider="modal")
        stage_raw = gtm_data.get("context", {}).get("stage", "Pre-Seed").lower()
        template = SCORING_GTM_PRE_SEED_PROMPT if "pre" in stage_raw else SCORING_GTM_SEED_PROMPT
        chain = PromptTemplate.from_template(template) | llm | StrOutputParser()
        
        raw_res = await chain.ainvoke({
            "current_date": datetime.now().strftime("%Y-%m-%d"),
            "gtm_data": json.dumps(gtm_data, indent=2),
            "economics_report": json.dumps(economics_report, indent=2),
            "contradiction_report": str(contradiction_report),
            "risk_report": str(risk_report)
        })
        
        result_dict = parse_and_repair_json(raw_res)
        result_dict["score_numeric"] = safe_score_numeric(result_dict)
        return result_dict