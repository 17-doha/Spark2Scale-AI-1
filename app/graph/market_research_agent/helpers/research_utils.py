import json
import http.client
import os
import pandas as pd
from app.core.config import Config, gemini_client
from app.core.rate_limiter import call_gemini
from app.graph.market_research_agent import prompts
from app.core.logger import get_logger

logger = get_logger("ResearchUtils")

SERPER_API_KEY = Config.SERPER_API_KEY

def generate_research_plan(idea, problem):
    logger.info(f"   🧠 Generating Comprehensive Research Plan for: '{idea}'...")
    try:
        prompt = prompts.generate_research_plan_prompt(idea, problem)
        response = call_gemini(prompt)
        return json.loads(response.text.replace("```json", "").replace("```", "").strip())
    except Exception as e:
        logger.error(f"Plan generation failed: {e}")
        return None

def generate_smart_queries(business_idea):
    # DEPRECATED: Use generate_research_plan instead
    logger.info(f"   🧠 Brainstorming search terms for: '{business_idea}'...")
    try:
        prompt = prompts.generate_smart_queries_prompt(business_idea)
        response = call_gemini(prompt)
        return json.loads(response.text.replace("```json", "").replace("```", "").strip())
    except Exception as e:
        logger.warning(f"Smart query generation failed: {e}")
        return None

def extract_competitors_strict(search_data, business_idea):
    """
    STRICT MODE: Extracts only Company Names. Filters out Blog Titles.
    """
    print(f"   🧪 Extracting Real App Names from {len(search_data)} results...")
    
    raw_text = ""
    for item in search_data:
        raw_text += f"- Title: {item.get('title')}\n  Snippet: {item.get('snippet')}\n\n"

    prompt = prompts.extract_competitors_prompt(business_idea, raw_text)
    
    try:
        response = call_gemini(prompt)
        return json.loads(response.text.replace("```json", "").replace("```", "").strip())
    except Exception as e:
        print(f"   ⚠️ Extraction Failed: {e}")
        return []

def execute_serper_search(queries):
    """
    Performs Serper Google Searches for a list of queries.
    """
    all_raw_results = []
    print(f"   🔎 executing {len(queries)} search queries...")
    
    # LIMIT TO 2 QUERIES TO SAVE QUOTA
    for q in queries[:2]:
        conn = http.client.HTTPSConnection("google.serper.dev")
        payload = json.dumps({ "q": q, "num": 5 })
        headers = { 'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json' }
        try:
            conn.request("POST", "/search", payload, headers)
            res = conn.getresponse()
            raw_response = res.read().decode("utf-8")
            data = json.loads(raw_response)
            if "organic" in data:
                all_raw_results.extend(data["organic"])
            else:
                print(f"   ⚠️ Serper No Results: {data}")
        except Exception as e:
            print(f"   ⚠️ Serper Request Failed: {e}")
    
    return all_raw_results

