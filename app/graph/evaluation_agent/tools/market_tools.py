import json
import os
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
from urllib.parse import urlparse


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
    VALUATION_RISK_MARKET_PROMPT_TEMPLATE,
    MARKET_SCORING_AGENT_PROMPT
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
async def regulation_trend_radar_tool(category: str, location: str):
    logger.info(f"📡 Radar Scan: '{category}' in '{location}'...")
    url = "https://google.serper.dev/search"
    headers = {'X-API-KEY': os.environ.get("SERPER_API_KEY"), 'Content-Type': 'application/json'}
    results_data = {}
    current_year = datetime.now().year

    async with aiohttp.ClientSession() as session:
        # Check 1: Regulations
        try:
            reg_q = f"{category} regulatory risks compliance laws {location}"
            async with session.post(url, headers=headers, json={"q": reg_q}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    hits = data.get("organic", [])[:3]
                    results_data["regulatory_evidence"] = "\n".join([f"- {r['snippet']}" for r in hits])
        except Exception as e:
            results_data["regulatory_evidence"] = f"Failed: {str(e)}"

        # Check 2: Trends
        try:
            trend_q = f"{category} market growth outlook {current_year} {location}"
            async with session.post(url, headers=headers, json={"q": trend_q}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    hits = data.get("organic", [])[:3]
                    results_data["trend_evidence"] = "\n".join([f"- {r['snippet']}" for r in hits])
        except Exception as e:
            results_data["trend_evidence"] = f"Failed: {str(e)}"

    return {"tool": "Regulation_Radar", "findings": results_data}
@retry(**RETRY_CONFIG)
async def tam_sam_verifier_tool(beachhead: str, location: str, claimed_size: str):
    logger.info(f"📊 TAM Check: '{beachhead}' in '{location}'...")
    if not os.environ.get("SERPER_API_KEY"):
        return {"tool": "TAM_Verifier", "status": "Simulated", "evidence": "Simulated: Market data not available."}

    search_query = f"total number of {beachhead} in {location} statistics {datetime.now().year}"
    url = "https://google.serper.dev/search"
    headers = {'X-API-KEY': os.environ.get("SERPER_API_KEY"), 'Content-Type': 'application/json'}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json={"q": search_query}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    snippets = [f"- {i.get('title')}: {i.get('snippet')}" for i in data.get("organic", [])[:3]]
                    return {
                        "tool": "TAM_Verifier",
                        "founder_claim": claimed_size,
                        "search_evidence": "\n".join(snippets),
                        "status": "Success"
                    }
        except Exception as e:
            return {"error": str(e)}
    return {"error": "Search Failed"}

async def local_dependency_detective(tech_stack: str, acquisition_channel: str, product_desc: str):
    async with concurrency_limiter:
        logger.info("🕵️ Dependency Detective...")
        llm = get_llm(temperature=0, provider="groq")
        prompt_text = f"""
        Analyze platform risks for Product: {product_desc}, Tech: {tech_stack}, Channel: {acquisition_channel}.
        Respond ONLY JSON: {{ "risk_level": "High/Medium/Low", "red_flags": ["..."], "search_query_needed": "..." }}
        """
        try:
            chain = StrOutputParser()
            resp_text = await llm.ainvoke(prompt_text)
            analysis = parse_and_repair_json(resp_text)
            return {"tool": "Dependency_Detective", "risk_level": analysis.get("risk_level"), "analysis": str(analysis)}
        except Exception as e:
            return {"tool": "Dependency_Detective", "error": str(e)}
@retry(**RETRY_CONFIG)
async def market_risk_agent(market_inputs, tam_result, radar_result, dep_result):
    async with concurrency_limiter:
        logger.info("📉 Market Risk...")
        llm = get_llm(temperature=0, provider="groq")
        chain = PromptTemplate.from_template(VALUATION_RISK_MARKET_PROMPT_TEMPLATE) | llm | StrOutputParser()
        return await chain.ainvoke({
            "internal_json": json.dumps(market_inputs, indent=2),
            "tam_report": json.dumps(tam_result, indent=2),
            "radar_report": json.dumps(radar_result, indent=2),
            "dependency_report": json.dumps(dep_result, indent=2)
        })

@retry(**RETRY_CONFIG)
async def market_scoring_agent(data_package: dict) -> dict:
    async with concurrency_limiter:
        logger.info("⚖️ Market Scoring...")
        llm = get_llm(temperature=0, provider="groq")
        chain = PromptTemplate.from_template(MARKET_SCORING_AGENT_PROMPT) | llm | StrOutputParser()
        
        raw_res = await chain.ainvoke({
            "current_date": datetime.now().strftime("%Y-%m-%d"),
            "internal_data": json.dumps(data_package.get("internal_data", {}), indent=2),
            "contradiction_report": str(data_package.get("contradiction_report", "None")),
            "tam_report": str(data_package.get("tam_report", "None")),
            "radar_report": str(data_package.get("radar_report", "None")),
            "dependency_report": str(data_package.get("dependency_report", "None"))
        })
        
        result_dict = parse_and_repair_json(raw_res)
        
        # Enrich
        result_dict["score_numeric"] = safe_score_numeric(result_dict)
        score_num = result_dict["score_numeric"] // 20 # back to 0-5 for rubric
        rubric_map = {0: "Undefined", 1: "Narrow", 2: "Medium", 3: "Large", 4: "Expanding", 5: "Blue Ocean"}
        result_dict["rubric_rating"] = rubric_map.get(score_num, "Unknown")
        return result_dict