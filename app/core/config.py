import os
from dotenv import load_dotenv
from google import genai
load_dotenv()

class Config:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    _raw_gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite").strip("'\"")
    GEMINI_MODEL = _raw_gemini_model if not _raw_gemini_model.startswith("AIzaSy") else "gemini-2.5-flash-lite"
    GEMINI_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0"))
    MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "2"))
    POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY")
    SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
    GEMINI_MODEL_NAME = GEMINI_MODEL
    _raw_image_model = os.getenv("IMAGE_MODEL", "gptimage-large")
    IMAGE_MODEL = _raw_image_model if not _raw_image_model.startswith("AIzaSy") else "gptimage-large"
    IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "pollinations")  # "pollinations" | "google"
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    OLLAMA_NUM_PARALLELL = int(os.getenv("OLLAMA_NUM_PARALLEL", "1"))
    OLLAMA_MAX_LOADED_MODELS = int(os.getenv("OLLAMA_MAX_LOADED_MODELS", "1"))
    GROQ_CONCURRENT_LIMIT = int(os.getenv("GROQ_CONCURRENT_LIMIT", "1"))
    LANGCHAIN_TRACING_V2 = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY", "")
    LANGCHAIN_PROJECT_NAME = os.getenv("LANGCHAIN_PROJECT_NAME", "spark2scale")
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
    NEO4J_URI = os.getenv("NEO4J_URI", "")
    NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")


    


load_dotenv(override=True)  # Override system environment variables with .env file



config = Config()
gemini_client = None

try:
    if hasattr(genai, "configure"):
        genai.configure(api_key=config.GEMINI_API_KEY)
        gemini_client = genai
    else:
        # New SDK support
        gemini_client = genai.Client(api_key=config.GEMINI_API_KEY) if config.GEMINI_API_KEY else None
except Exception as e:
    print(f"Warning: Failed to initialize Gemini client: {e}")
