import os
import aiohttp
import asyncio
from app.core.logger import get_logger

logger = get_logger(__name__)

async def execute_search_queries(queries: list) -> str:
    """Runs search using Google Serper API via Async HTTP for a list of queries."""
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        logger.warning("No Serper API Key found. Validation may fail or mock.")
        return "No real search results available (Missing API Key)."

    url = "https://google.serper.dev/search"
    headers = {
        'X-API-KEY': api_key,
        'Content-Type': 'application/json'
    }
    
    raw_results = []
    
    async def fetch_query(session, q):
        try:
            async with session.post(url, headers=headers, json={"q": q}) as response:
                if response.status == 200:
                    data = await response.json()
                    organic = data.get('organic', [])[:3] 
                    return [f"Query: {q}\\nTitle: {r.get('title')}\\nSnippet: {r.get('snippet')}" for r in organic]
        except Exception as e:
            logger.error(f"Serper error for query '{q}': {e}")
        return []

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_query(session, q) for q in queries]
        results_list = await asyncio.gather(*tasks)
        
        for res in results_list:
            raw_results.extend(res)

    return "\\n".join(raw_results) if raw_results else "No relevant search results found."
