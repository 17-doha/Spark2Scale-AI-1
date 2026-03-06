import os
import asyncio
import itertools
import threading
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.chat_models import ChatOllama
from langchain_groq import ChatGroq  
from app.core.config import Config
try:
    from gradio_client import Client as GradioClient
except ImportError:
    GradioClient = None

# =========================================================
# GROQ API KEY ROTATION (Round-Robin across multiple keys)
# =========================================================
_groq_keys = [
    os.getenv(f"GROQ_API_KEY_{i}") 
    for i in range(1, 5) 
    if os.getenv(f"GROQ_API_KEY_{i}")
]

# Fallback: use single key if numbered keys aren't set
if not _groq_keys and Config.GROQ_API_KEY:
    _groq_keys = [Config.GROQ_API_KEY]

_groq_key_cycle = itertools.cycle(_groq_keys) if _groq_keys else None
_groq_key_lock = threading.Lock()

def _get_next_groq_key() -> str:
    """Thread-safe round-robin key selection."""
    if not _groq_key_cycle:
        raise ValueError("No GROQ API keys configured. Set GROQ_API_KEY_1 through GROQ_API_KEY_4 in .env")
    with _groq_key_lock:
        return next(_groq_key_cycle)

def get_llm(temperature=None, provider="gemini", model_name=None):
    """
    Factory function to get the LLM instance.
    
    Args:
        temperature (float): Creativity (0.0 to 1.0).
        provider (str): "gemini", "ollama", or "groq".
        model_name (str): Optional override (e.g., "llama3-70b-8192").
    """
    final_temp = temperature if temperature is not None else Config.GEMINI_TEMPERATURE

    # --- OPTION 1: GROQ (Fastest / Recommended for Logic) ---
    if provider == "groq":
        selected_model = model_name if model_name else "llama-3.1-8b-instant"
        
        # Round-robin key rotation for higher effective RPM
        api_key = _get_next_groq_key()

        return ChatGroq(
            temperature=final_temp,
            model_name=selected_model,
            api_key=api_key,
            max_retries=6,
            request_timeout=90,
            timeout=90 
        )

    # --- OPTION 2: OLLAMA (Local) ---
    if provider == "ollama":
        selected_model = model_name if model_name else "gemma3:1b"
        
        return ChatOllama(
            model=selected_model,
            format="json", 
            temperature=final_temp,
            base_url=getattr(Config, 'OLLAMA_BASE_URL', "http://localhost:11434")
        )

    if not Config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set in the environment variables.")

    return ChatGoogleGenerativeAI(
        model=Config.GEMINI_MODEL,
        temperature=final_temp,
        google_api_key=Config.GEMINI_API_KEY,
        convert_system_message_to_human=True,
        request_timeout=60  
    )


# =========================================================
# T5-3B  (Hugging Face Space via Gradio — lazy-connect)
# =========================================================
_T5_SPACE_URL = "Dohahemdann/Spark2Scale-Space"
_t5_gradio_client = None
_t5_client_lock = threading.Lock()

def _get_t5_client():
    """
    Returns a live GradioClient, creating it on first call.
    Thread-safe; reuses the same connection across all requests.
    """
    global _t5_gradio_client
    if _t5_gradio_client is not None:
        return _t5_gradio_client
    if GradioClient is None:
        return None
    with _t5_client_lock:
        # Double-checked locking
        if _t5_gradio_client is not None:
            return _t5_gradio_client
        try:
            hf_token = os.getenv("HF_TOKEN") or ""
            _t5_gradio_client = GradioClient(_T5_SPACE_URL, token=hf_token)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("T5 Gradio client failed: %s", e)
            _t5_gradio_client = None
    return _t5_gradio_client


async def get_t5_insight(prompt: str) -> str:
    """
    Calls the fine-tuned T5-3B model on Hugging Face Spaces.

    Available to **any** agent via::

        from app.core.llm import get_t5_insight
        result = await get_t5_insight("Evaluate this startup ...")

    The blocking Gradio predict() call runs in a background thread so the
    async event loop stays free for Groq / search tasks running in parallel.

    Returns:
        str: Raw text from the T5 model, or a fallback message on failure.
    """
    client = await asyncio.to_thread(_get_t5_client)
    if client is None:
        return "T5 Model unavailable (gradio_client not installed or Space unreachable)."
    try:
        result = await asyncio.to_thread(
            client.predict,
            startup_idea=prompt,
            api_name="/evaluate_idea"
        )
        return str(result)
    except Exception as e:
        return f"T5 Insight failed: {str(e)}"
