import json
import os
import aiohttp
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
from ..prompts.prompts import (
    OPERATIONS_SCORING_AGENT_PROMPT
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
async def get_funding_benchmarks(location: str, stage: str, sector: str) -> str:
    logger.info(f"💰 Searching Benchmarks for {stage} {sector} in {location}...")
    url = "https://google.serper.dev/search"
    headers = {'X-API-KEY': os.environ.get("SERPER_API_KEY"), 'Content-Type': 'application/json'}
    current_year = datetime.now().year
    
    queries = [
        f"average {stage} {sector} startup round size {location} {current_year}",
        f"average {stage} {sector} startup valuation {location} {current_year}"
    ]
    results = []
    
    async with aiohttp.ClientSession() as session:
        for q in queries:
            try:
                async with session.post(url, headers=headers, json={"q": q}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for r in data.get('organic', [])[:2]:
                            results.append(f"SOURCE: {r.get('title')} - {r.get('snippet')}")
            except Exception: pass
            
    return "\n".join(results) if results else "No specific benchmarks found."

@retry(**RETRY_CONFIG)
async def operations_risk_agent(operations_data: dict, benchmarks: str, template: str) -> str:
    async with concurrency_limiter:
        llm = get_llm(temperature=0, provider="groq")
        chain = PromptTemplate.from_template(template) | llm | StrOutputParser()
        return await chain.ainvoke({
            "operations_data": json.dumps(operations_data, indent=2),
            "benchmarks": benchmarks
        })

@retry(**RETRY_CONFIG)
async def operations_scoring_agent(data_package: dict) -> dict:
    async with concurrency_limiter:
        logger.info("⚖️ Operations Scoring...")
        llm = get_llm(temperature=0, provider="groq")
        chain = PromptTemplate.from_template(OPERATIONS_SCORING_AGENT_PROMPT) | llm | StrOutputParser()
        
        raw_res = await chain.ainvoke({
            "current_date": datetime.now().strftime("%Y-%m-%d"),
            "operations_data": json.dumps(data_package.get("operations_data", {}), indent=2),
            "benchmarks": str(data_package.get("benchmarks", "None")),
            "contradiction_report": str(data_package.get("contradiction_report", "None")),
            "risk_report": str(data_package.get("risk_report", "None"))
        })
        
        result_dict = parse_and_repair_json(raw_res)
        result_dict["score_numeric"] = safe_score_numeric(result_dict)
        return result_dict