import json
import os
import asyncio
import aiohttp


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
    PROBLEM_SCORING_AGENT_PROMPT
  
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
async def verify_problem_claims(problem_statement: str, target_audience: str) -> dict:
    logger.info("🔎 Verifying Problem Claims...")
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key: return {"error": "Missing SERPER_API_KEY."}

    # 1. Generate Queries
    async with concurrency_limiter:
        llm = get_llm(temperature=0, provider="groq")
        query_gen_prompt = f"""
        Search Expert. Convert to 3 Google queries.
        Audience: {target_audience}
        Problem: {problem_statement}
        Output JSON ONLY: {{"pain_query": "...", "symptom_query": "...", "solution_query": "..."}}
        """
        try:
            resp = await llm.ainvoke(query_gen_prompt)
            queries = parse_and_repair_json(resp.content)
            if not isinstance(queries, dict): raise ValueError
        except:
            queries = {"pain_query": f"{problem_statement} reddit", "symptom_query": f"{target_audience} struggle", "solution_query": f"solution {problem_statement}"}

    # 2. Execute Search (Async IO)
    url = "https://google.serper.dev/search"
    headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
    results_report = {"generated_queries": queries, "pain_validation_search": [], "competitor_search": []}

    async def run_single_search(session, q):
        try:
            async with session.post(url, headers=headers, json={"q": q, "num": 4}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return [{"title": r.get("title"), "link": r.get("link"), "snippet": r.get("snippet")} for r in data.get("organic", [])]
        except: return []
        return []

    async with aiohttp.ClientSession() as session:
        pain, symptom, sol = await asyncio.gather(
            run_single_search(session, queries.get("pain_query")),
            run_single_search(session, queries.get("symptom_query")),
            run_single_search(session, queries.get("solution_query"))
        )
        results_report["pain_validation_search"] = pain + symptom
        results_report["competitor_search"] = sol

    return results_report

@retry(**RETRY_CONFIG)
async def problem_scoring_agent(data_package: dict) -> dict:
    async with concurrency_limiter:
        logger.info("🏆 Problem Scoring...")
        llm = get_llm(temperature=0, provider="groq")
        chain = PromptTemplate.from_template(PROBLEM_SCORING_AGENT_PROMPT) | llm | StrOutputParser()
        
        inputs = {
            "problem_json": json.dumps(data_package.get("problem_definition", {}), indent=2),
            "missing_report": str(data_package.get("missing_report")),
            # Optimization: Don't send full JSON search results, just titles/snippets if possible to save tokens
            "search_json": json.dumps(data_package.get("search_report", {}), indent=2),
            "risk_report": str(data_package.get("risk_report")),
            "contradiction_report": str(data_package.get("contradiction_report"))
        }

        try:
            raw_res = await asyncio.wait_for(chain.ainvoke(inputs), timeout=30.0)
            result_dict = parse_and_repair_json(raw_res)
            result_dict["score_numeric"] = safe_score_numeric(result_dict)
            return result_dict
            
        except asyncio.TimeoutError:
            logger.warning("⏰ Groq took too long! Retrying...")
            raise TimeoutError("Groq Request Timed Out")
