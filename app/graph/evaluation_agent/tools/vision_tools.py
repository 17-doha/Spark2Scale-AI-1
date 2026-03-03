import json
from datetime import datetime
import os


# LangChain & AI Imports
import aiohttp
import aiohttp
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError
from google.api_core.exceptions import ResourceExhausted
from groq import APIStatusError as GroqAPIStatusError

# Resilience
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Relative Imports
from ..prompts.general_prompts import (
    CATEGORY_FUTURE_PROMPT
)
from ..prompts.vision_prompts import (
    VISION_SCORING_AGENT_PROMPT
)
from ..helpers import (
     check_missing_fields,
    get_market_signals_serper, get_market_signals_duckduckgo,
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
async def analyze_category_future(vision_data: dict) -> dict:
    logger.info("🌐 Vision Market Analysis...")
    try:
        # Search Phase
        market_text = await get_market_signals_serper(vision_data)
        if "No Serper results" in market_text:
            ddg_text = get_market_signals_duckduckgo(vision_data)
            combined_signals = f"=== DUCKDUCKGO ===\n{ddg_text}"
        else:
            combined_signals = f"=== SERPER ===\n{market_text}"
        
        # LLM Phase (Sequential)
        async with concurrency_limiter:
            logger.info("🌐 Vision Analysis (LLM)...")
            llm = get_llm(temperature=0, provider="groq")
            prompt = PromptTemplate.from_template(CATEGORY_FUTURE_PROMPT)
            chain = prompt | llm | StrOutputParser()
            
            raw_res = await chain.ainvoke({
                "category": vision_data.get("category_play", {}).get("definition", "Unknown"),
                "problem": vision_data.get("customer_obsession", {}).get("problem_statement", "Unknown"),
                "moat": f"{vision_data.get('category_play', {}).get('moat')}",
                "market_signals": combined_signals
            })
            return parse_and_repair_json(raw_res)
    except Exception as e:
        return {"error": str(e)}
@retry(**RETRY_CONFIG)
async def vision_risk_agent(vision_data: dict, market_analysis: dict, template: str) -> str:
    async with concurrency_limiter:
        llm = get_llm(temperature=0, provider="groq")
        chain = PromptTemplate.from_template(template) | llm | StrOutputParser()
        return await chain.ainvoke({
            "vision_data": json.dumps(vision_data, indent=2),
            "market_analysis": json.dumps(market_analysis, indent=2)
        })
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
async def vision_scoring_agent(data_package: dict) -> dict:
    async with concurrency_limiter:
        logger.info("⚖️ Vision Scoring...")
        llm = get_llm(temperature=0, provider="groq")
        chain = PromptTemplate.from_template(VISION_SCORING_AGENT_PROMPT) | llm | StrOutputParser()
        
        raw_res = await chain.ainvoke({
            "current_date": datetime.now().strftime("%Y-%m-%d"),
            "vision_data": json.dumps(data_package.get("vision_data", {}), indent=2),
            "market_analysis": json.dumps(data_package.get("market_analysis", {}), indent=2),
            "contradiction_report": str(data_package.get("contradiction_report", "None")),
            "risk_report": str(data_package.get("risk_report", "None"))
        })
        
        result_dict = parse_and_repair_json(raw_res)
        result_dict["score_numeric"] = safe_score_numeric(result_dict)
        return result_dict