import os
import asyncio
import itertools
import threading
import aiohttp
import requests
from typing import Any, Optional, List
from langchain_core.language_models.llms import LLM
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.chat_models import ChatOllama
from langchain_groq import ChatGroq  
from app.core.config import Config
try:
    from gradio_client import Client as GradioClient
except ImportError:
    GradioClient = None

# =========================================================
# MODAL CUSTOM LANGCHAIN WRAPPER
# =========================================================
# The deployed /infer endpoint expects:
#   { context, question, json_mode, temperature, max_new_tokens, top_p, top_k }
# and returns:
#   { answer, inference_time, json_data?, json_valid?, json_error? }
#
# LangChain chains pass a single `prompt` string.
# We split on the first double-newline to extract context vs question.
# If no separator is found the whole text becomes the question.

_MODAL_INFER_URL = os.getenv(
    "MODAL_INFER_URL",
    "https://doha-hemdan7--spark2scale-gemma3n-inference-llmengine-infer.modal.run",
)

class ModalCustomLLM(LLM):
    """LangChain wrapper for the Modal-deployed Gemma 3n /infer endpoint."""

    endpoint_url: str = _MODAL_INFER_URL
    temperature:  float = 0.7
    max_tokens:   int   = 1024   # output tokens; rest of the 8192 window goes to the prompt
    json_mode:    bool  = False

    @property
    def _llm_type(self) -> str:
        return "modal_gemma3n"

    # ── helper: split prompt into (context, question) ────────────────────────
    @staticmethod
    def _split_prompt(prompt: str):
        """
        Convention used by evaluation_agent chains:
          <system/data block>
          \n\n
          <instruction / scoring request>
        Everything before the FIRST double blank line → context.
        Everything after                              → question.
        """
        parts = prompt.split("\n\n", 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
        return "", prompt.strip()

    # ── sync call (used by .invoke()) ────────────────────────────────────────
    def _call(self, prompt: str, stop: Optional[List[str]] = None, **kwargs: Any) -> str:
        context, question = self._split_prompt(prompt)
        payload = {
            "context":        context,
            "question":       question,
            "json_mode":      self.json_mode,
            "temperature":    self.temperature,
            "max_new_tokens": self.max_tokens,
        }
        response = requests.post(self.endpoint_url, json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()
        # If the model returned valid JSON and caller asked for json_mode,
        # prefer the pre-parsed dict stringified, else return raw answer.
        if self.json_mode and data.get("json_valid"):
            import json as _json
            return _json.dumps(data["json_data"])
        return data.get("answer", "")

    # ── async call (used by .ainvoke()) ──────────────────────────────────────
    async def _acall(
        self, prompt: str, stop: Optional[List[str]] = None, **kwargs: Any
    ) -> str:
        context, question = self._split_prompt(prompt)
        payload = {
            "context":        context,
            "question":       question,
            "json_mode":      self.json_mode,
            "temperature":    self.temperature,
            "max_new_tokens": self.max_tokens,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.endpoint_url, json=payload, timeout=aiohttp.ClientTimeout(total=300)
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                if self.json_mode and data.get("json_valid"):
                    import json as _json
                    return _json.dumps(data["json_data"])
                return data.get("answer", "")

# =========================================================
# GROQ API KEY ROTATION
# =========================================================
_groq_keys = [
    os.getenv(f"GROQ_API_KEY_{i}") 
    for i in range(1, 5) 
    if os.getenv(f"GROQ_API_KEY_{i}")
]

if not _groq_keys and getattr(Config, 'GROQ_API_KEY', None):
    _groq_keys = [Config.GROQ_API_KEY]

_groq_key_cycle = itertools.cycle(_groq_keys) if _groq_keys else None
_groq_key_lock = threading.Lock()

def _get_next_groq_key() -> str:
    if not _groq_key_cycle:
        raise ValueError("No GROQ API keys configured.")
    with _groq_key_lock:
        return next(_groq_key_cycle)


def get_llm(temperature=None, provider="gemini", model_name=None):
    final_temp = temperature if temperature is not None else getattr(Config, 'GEMINI_TEMPERATURE', 0.7)

    # --- NEW OPTION: MODAL (Gemma 3n fine-tuned on A100) ---
    if provider == "modal":
        return ModalCustomLLM(
            # endpoint_url defaults to _MODAL_INFER_URL
            temperature = final_temp,
            max_tokens  = 1024,   # output reservation; rest of the 8192-token window is for the prompt
            json_mode   = True,   # chains always expect structured JSON output
        )

    # --- OPTION 1: GROQ ---
    if provider == "groq":
        selected_model = model_name if model_name else "llama-3.1-8b-instant"
        api_key = _get_next_groq_key()
        return ChatGroq(
            temperature=final_temp,
            model_name=selected_model,
            api_key=api_key,
            max_retries=6,
            request_timeout=90,
            timeout=90 
        )

    # --- OPTION 2: OLLAMA ---
    if provider == "ollama":
        selected_model = model_name if model_name else "gemma3:1b"
        return ChatOllama(
            model=selected_model,
            format="json", 
            temperature=final_temp,
            base_url=getattr(Config, 'OLLAMA_BASE_URL', "http://localhost:11434")
        )

    # --- OPTION 3: GEMINI ---
    if not getattr(Config, 'GEMINI_API_KEY', None):
        raise ValueError("GEMINI_API_KEY is not set.")

    return ChatGoogleGenerativeAI(
        model=getattr(Config, 'GEMINI_MODEL', 'gemini-1.5-flash'),
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
