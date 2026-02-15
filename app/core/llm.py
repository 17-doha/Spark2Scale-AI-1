import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.chat_models import ChatOllama
from langchain_groq import ChatGroq  
from app.core.config import Config

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
        # Default to a fast, smart model like Llama 3 70B if not specified
        selected_model = model_name if model_name else "llama-3.1-8b-instant"
        
        api_key = Config.GROQ_API_KEY
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set.")

        return ChatGroq(
            temperature=final_temp,
            model_name=selected_model,
            api_key=api_key,
            max_retries=2,
            # Groq is fast, so we can set a short timeout
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