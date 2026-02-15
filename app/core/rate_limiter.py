import time
import asyncio
import random
from app.core.config import Config
from app.core.llm import get_llm
from app.graph.market_research_agent.logger_config import get_logger

logger = get_logger("RateLimiter")

class GeminiResponseWrapper:
    """Wraps LangChain output to mimic the legacy Gemini response object (.text attribute)."""
    def __init__(self, content):
        self.text = content

class GeminiLimiter:
    _last_call_time = 0
    _min_interval = 7.0 

    @classmethod
    def call_gemini(cls, model_name, prompt, retries=3):
        """
        Thread-safe(ish) wrapper for Gemini API calls with rate limiting.
        """
        # 1. Enforce Rate Limit
        elapsed = time.time() - cls._last_call_time
        if elapsed < cls._min_interval:
            wait_time = cls._min_interval - elapsed
            logger.info(f"⏳ Rate Limit: Waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
        
        cls._last_call_time = time.time()

        # 2. Execute with Retry Logic
        for attempt in range(retries):
            try:
                # Use the centralized LLM factory (LangChain)
                llm = get_llm(provider="gemini", model_name=model_name)
                response = llm.invoke(prompt)
                
                # Wrap it to match the expected interface (response.text)
                return GeminiResponseWrapper(response.content)
                
            except Exception as e: # Catch broadly
                error_str = str(e)
                # Check for quota errors (LangChain/Google might raise different exceptions, keeping checks broad)
                if "429" in error_str or "ResourceExhausted" in error_str or "Quota exceeded" in error_str or "429" in str(type(e)):
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"⚠️ Quota Hit (429). Retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
                    cls._last_call_time = time.time() # Reset timer after wait
                else:
                    raise e # Re-raise non-quota errors
        
        raise Exception("Max retries exceeded for Gemini API call.")

def call_gemini(prompt, model_name=None):
    if not model_name:
        model_name = Config.GEMINI_MODEL_NAME
    return GeminiLimiter.call_gemini(model_name, prompt)
