import os
from dotenv import load_dotenv
from google import genai
load_dotenv()

class Config:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    GEMINI_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.7"))
    MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "2"))
    POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY")
    SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
    GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    # Image generation:
    # - Provider is configured via IMAGE_PROVIDER: "pollinations" (default) or "google" (Gemini image model).
    # - IMAGE_MODEL controls the underlying model name for that provider.
    IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gptimage-large")
    IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "pollinations")  # "pollinations" | "google"


load_dotenv(override=True)  # Override system environment variables with .env file



config = Config()
gemini_client = None

try:
    genai.configure(api_key=config.GEMINI_API_KEY)
    gemini_client = genai
except Exception as e:
    print(f"Warning: Failed to initialize Gemini client: {e}")

