import json


# LangChain & AI Imports
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError
from google.api_core.exceptions import ResourceExhausted
from groq import APIStatusError as GroqAPIStatusError

# Resilience
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Relative Imports
from ..prompts.team_prompts import (
    TEAM_SCORING_AGENT_PROMPT
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
async def team_risk_check(data: dict, agent_prompt: str) -> str:
    async with concurrency_limiter:
        logger.info("📉 Team Risk Check...")
        llm = get_llm(temperature=0, provider="modal")
        chain = PromptTemplate.from_template(agent_prompt) | llm | StrOutputParser()
        return await chain.ainvoke({"json_data": json.dumps(data, indent=2)})


@retry(**RETRY_CONFIG)
async def team_scoring_agent(data_package: dict) -> dict:
    async with concurrency_limiter:
        logger.info("🏆 Team Scoring...")
        llm = get_llm(temperature=0, provider="modal")
        # Use StrOutputParser + repair_json
        chain = PromptTemplate.from_template(TEAM_SCORING_AGENT_PROMPT) | llm | StrOutputParser()
        
        raw_res = await chain.ainvoke({
            "user_json_data": json.dumps(data_package.get("user_data", {}), indent=2),
            "risk_agent_output": str(data_package.get("risk_report")),
            "contradiction_agent_output": str(data_package.get("contradiction_report")),
            "missing_info_output": str(data_package.get("missing_report"))
        })
        
        result_dict = parse_and_repair_json(raw_res)
        result_dict["score_numeric"] = safe_score_numeric(result_dict)
        return result_dict