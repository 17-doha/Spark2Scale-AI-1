import os
from dotenv import load_dotenv
import google.generativeai as genai
load_dotenv()

class Config:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    GEMINI_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0"))
    MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "2"))
    POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY")
    SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
    GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    # Image generation:
    # - Provider is configured via IMAGE_PROVIDER: "pollinations" (default) or "google" (Gemini image model).
    # - IMAGE_MODEL controls the underlying model name for that provider.
    IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gptimage-large")
    IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "pollinations")  # "pollinations" | "google"
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    OLLAMA_NUM_PARALLELL = int(os.getenv("OLLAMA_NUM_PARALLEL", "1"))
    OLLAMA_MAX_LOADED_MODELS = int(os.getenv("OLLAMA_MAX_LOADED_MODELS", "1"))
    GROQ_CONCURRENT_LIMIT = int(os.getenv("GROQ_CONCURRENT_LIMIT", "1"))
    LANGCHAIN_TRACING_V2 = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY", "")
    LANGCHAIN_PROJECT_NAME = os.getenv("LANGCHAIN_PROJECT_NAME", "spark2scale")


    


load_dotenv(override=True)  # Override system environment variables with .env file



config = Config()
gemini_client = None

try:
    genai.configure(api_key=config.GEMINI_API_KEY)
    gemini_client = genai
except Exception as e:
    print(f"Warning: Failed to initialize Gemini client: {e}")

