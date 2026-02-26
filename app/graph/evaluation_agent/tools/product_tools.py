import json
import asyncio
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
    PRODUCT_SCORING_AGENT_PROMPT,
    
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
async def tech_stack_detective(url: str):
    logger.info(f"🛠️ Tech Stack Detective: {url}")
    if not url: return {"verdict": "No URL"}
    try:
        tech_data = await asyncio.to_thread(builtwith.parse, url)
        detected = [item for sublist in tech_data.values() for item in sublist]
        return {"technologies_found": detected, "status": "Success"}
    except Exception as e:
        return {"error": str(e)}

# @retry(**RETRY_CONFIG)
# async def analyze_visuals_with_langchain(company_name, website_url, prompt_template):
#     if not website_url: return "No URL."
#     capture = await capture_screenshot(website_url)
#     if "error" in capture: return f"Visual Error: {capture['error']}"

#     async with concurrency_limiter:
#         logger.info("👁️ Vision Analysis...")
#         # Vision requires Gemini (Groq doesn't do image inputs well yet usually)
#         llm = get_llm(temperature=0, provider="gemini") 
#         msg = HumanMessage(content=[
#             {"type": "text", "text": prompt_template.format(company_name=company_name, website_url=website_url)},
#             {"type": "image_url", "image_url": f"data:image/png;base64,{capture['image_b64']}"}
#         ])
#         resp = await llm.ainvoke([msg])
#         return resp.content

@retry(**RETRY_CONFIG)
async def product_scoring_agent(data_package: dict) -> dict:
    async with concurrency_limiter:
        logger.info("🏆 Product Scoring...")
        llm = get_llm(temperature=0, provider="groq")
        chain = PromptTemplate.from_template(PRODUCT_SCORING_AGENT_PROMPT) | llm | StrOutputParser()
        
        raw_res = await chain.ainvoke({
            "current_date": datetime.now().strftime("%Y-%m-%d"),
            "internal_data": json.dumps(data_package.get("internal_data", {}), indent=2),
            "contradiction_report": str(data_package.get("contradiction_report")),
            "risk_report": str(data_package.get("risk_report")),
            "tech_stack_report": str(data_package.get("tech_stack_report")),
            "visual_analysis_report": str(data_package.get("visual_analysis_report"))
        })
        
        result_dict = parse_and_repair_json(raw_res)
        result_dict["score_numeric"] = safe_score_numeric(result_dict)
        return result_dict