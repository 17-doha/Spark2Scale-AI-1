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
# The deployed /infer endpoint supports two calling conventions:
#
#  A) Legacy  — context + question fields (evaluation_agent / chat.py)
#       { context, question, json_mode, temperature, max_new_tokens }
#
#  B) Passthrough — pre-built prompt (PDF extractor node)
#       { prompt, temperature, max_new_tokens }
#
# Convention B is selected when the prompt string starts with the
# sentinel prefix _PROMPT_PASSTHROUGH_PREFIX, which node.py prepends.
# This avoids _split_prompt() from tearing the schema apart on \n\n.

_MODAL_INFER_URL = os.getenv(
    "MODAL_INFER_URL",
    "https://doha-hemdan7--spark2scale-gemma3n-inference-llmengine-infer.modal.run",
)

# Sentinel that node.py prepends so the wrapper knows NOT to split the prompt
_PROMPT_PASSTHROUGH_PREFIX = "__PASSTHROUGH__:"


class ModalCustomLLM(LLM):
    """LangChain wrapper for the Modal-deployed Gemma 3n /infer endpoint."""

    endpoint_url: str = _MODAL_INFER_URL
    temperature:  float = 0.7
    max_tokens:   int   = 1024
    json_mode:    bool  = False

    @property
    def _llm_type(self) -> str:
        return "modal_gemma3n"

    # ── Detect calling convention ─────────────────────────────────────────────
    @staticmethod
    def _is_passthrough(prompt: str) -> bool:
        return prompt.startswith(_PROMPT_PASSTHROUGH_PREFIX)

    @staticmethod
    def _strip_prefix(prompt: str) -> str:
        return prompt[len(_PROMPT_PASSTHROUGH_PREFIX):]

    # ── Legacy helper: split prompt into (context, question) ─────────────────
    @staticmethod
    def _split_prompt(prompt: str):
        """
        Convention used by evaluation_agent chains:
          <system/data block>  \\n\\n  <instruction>
        Everything before the FIRST double blank line → context.
        Everything after                              → question.
        """
        parts = prompt.split("\n\n", 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
        return "", prompt.strip()

    # ── Build payload for each convention ────────────────────────────────────
    def _build_payload(self, prompt: str) -> dict:
        if self._is_passthrough(prompt):
            # PDF-extractor path: send the full prompt as-is, no splitting.
            # json_mode is intentionally False here — the prompt already
            # contains all extraction instructions; the Modal side must NOT
            # append an extra JSON suffix that wastes tokens and confuses the model.
            return {
                "prompt":         self._strip_prefix(prompt),
                "temperature":    self.temperature,
                "max_new_tokens": self.max_tokens,
                "json_mode":      False,   # handled by the prompt itself
            }
        else:
            # Legacy path: evaluation_agent / chat.py
            context, question = self._split_prompt(prompt)
            return {
                "context":        context,
                "question":       question,
                "json_mode":      self.json_mode,
                "temperature":    self.temperature,
                "max_new_tokens": self.max_tokens,
            }

    # ── Parse response ────────────────────────────────────────────────────────
    @staticmethod
    def _parse_response(data: dict, json_mode: bool, is_passthrough: bool) -> str:
        import json as _json
        if (json_mode or is_passthrough) and data.get("json_valid"):
            return _json.dumps(data["json_data"])
        return data.get("answer", "")

    # ── Sync call (used by .invoke()) ─────────────────────────────────────────
    def _call(self, prompt: str, stop: Optional[List[str]] = None, **kwargs: Any) -> str:
        passthrough = self._is_passthrough(prompt)
        payload     = self._build_payload(prompt)
        response    = requests.post(self.endpoint_url, json=payload, timeout=300)
        response.raise_for_status()
        return self._parse_response(response.json(), self.json_mode, passthrough)

    # ── Async call (used by .ainvoke()) ───────────────────────────────────────
    async def _acall(
        self, prompt: str, stop: Optional[List[str]] = None, **kwargs: Any
    ) -> str:
        passthrough = self._is_passthrough(prompt)
        payload     = self._build_payload(prompt)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.endpoint_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=300),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return self._parse_response(data, self.json_mode, passthrough)


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
_groq_key_lock  = threading.Lock()


def _get_next_groq_key() -> str:
    if not _groq_key_cycle:
        raise ValueError("No GROQ API keys configured.")
    with _groq_key_lock:
        return next(_groq_key_cycle)


def get_llm(temperature=None, provider="gemini", model_name=None, json_mode: bool = False):
    """
    Factory for LLM instances.

    Parameters
    ----------
    json_mode : bool
        Only relevant for provider="modal" on legacy (context+question) calls.
        Do NOT set this to True for PDF extraction — the prompt already
        contains all instructions and the Modal side must not append extras.
    """
    final_temp = temperature if temperature is not None else getattr(Config, 'GEMINI_TEMPERATURE', 0.7)

    if provider == "modal":
        return ModalCustomLLM(
            temperature = final_temp,
            max_tokens  = 1024,
            json_mode   = json_mode,   # caller decides; default False
        )

    if provider == "groq":
        selected_model = model_name or "llama-3.1-8b-instant"
        api_key = _get_next_groq_key()
        return ChatGroq(
            temperature    = final_temp,
            model_name     = selected_model,
            api_key        = api_key,
            max_retries    = 6,
            request_timeout= 90,
            timeout        = 90,
        )

    if provider == "ollama":
        selected_model = model_name or "gemma3:1b"
        return ChatOllama(
            model      = selected_model,
            format     = "json",
            temperature= final_temp,
            base_url   = getattr(Config, 'OLLAMA_BASE_URL', "http://localhost:11434"),
        )

    if not getattr(Config, 'GEMINI_API_KEY', None):
        raise ValueError("GEMINI_API_KEY is not set.")

    return ChatGoogleGenerativeAI(
        model       = getattr(Config, 'GEMINI_MODEL', 'gemini-1.5-flash'),
        temperature = final_temp,
        google_api_key          = Config.GEMINI_API_KEY,
        convert_system_message_to_human = True,
        request_timeout         = 60,
    )


# =========================================================
# T5-3B  (Hugging Face Space via Gradio — lazy-connect)
# =========================================================
_T5_SPACE_URL      = "Dohahemdann/Spark2Scale-Space"
_t5_gradio_client  = None
_t5_client_lock    = threading.Lock()


def _get_t5_client():
    global _t5_gradio_client
    if _t5_gradio_client is not None:
        return _t5_gradio_client
    if GradioClient is None:
        return None
    with _t5_client_lock:
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
    The blocking Gradio predict() runs in a background thread.
    """
    client = await asyncio.to_thread(_get_t5_client)
    if client is None:
        return "T5 Model unavailable (gradio_client not installed or Space unreachable)."
    try:
        result = await asyncio.to_thread(
            client.predict,
            startup_idea=prompt,
            api_name="/evaluate_idea",
        )
        return str(result)
    except Exception as e:
        return f"T5 Insight failed: {str(e)}"