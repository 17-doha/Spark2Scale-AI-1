import os
import itertools
import threading
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.chat_models import ChatOllama
from langchain_groq import ChatGroq  
from app.core.config import Config

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
            request_timeout=30 
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
