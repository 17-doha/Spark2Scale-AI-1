import os
import logging
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
    
    if provider == "gemma":
        raise ValueError(
            "Gemma is not a LangChain LLM — use get_gemma_insight() or "
            "get_gemma_insight_async() directly from app.core.llm"
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


# =========================================================
# GEMMA 3n Spark2Scale  (finetuned model via ngrok + vLLM)
# =========================================================
import requests as _requests
import aiohttp as _aiohttp
import json as _json

_GEMMA_NGROK_URL = os.getenv("GEMMA_NGROK_URL", "").rstrip("/")

# Dedicated logger for Gemma calls — verbose step tracking
_gemma_logger = logging.getLogger("app.core.llm.gemma")

# vLLM serves an OpenAI-compatible API; long inference can take minutes
_GEMMA_TIMEOUT_SECONDS = 600  # 10 min hard ceiling for large prompts


# ------------------------------------------------------------------
# SYNC helper (used by document_chat answer_query_node / tests)
# ------------------------------------------------------------------
def get_gemma_insight(
    context: str,
    question: str,
    json_mode: bool = False,
    temperature: float = 1.0,
    max_new_tokens: int = 512,
) -> str:
    """
    Synchronous call to the finetuned Gemma model running on Colab via ngrok.

    The server is expected to expose a /infer endpoint compatible with the
    document-chat payload format.

    Usage in any agent::

        from app.core.llm import get_gemma_insight
        result = get_gemma_insight(context="...", question="...")
    """
    _gemma_logger.info(
        "[Gemma-SYNC] ▶ Starting inference | url=%s | json_mode=%s | "
        "max_new_tokens=%d | temperature=%.2f",
        _GEMMA_NGROK_URL, json_mode, max_new_tokens, temperature,
    )

    if not _GEMMA_NGROK_URL:
        _gemma_logger.error("[Gemma-SYNC] ✗ GEMMA_NGROK_URL is not set in .env")
        return "Gemma model unavailable: GEMMA_NGROK_URL not set in .env"

    payload = {
        "context":        context,
        "question":       question,
        "json_mode":      json_mode,
        "temperature":    temperature,
        "max_new_tokens": max_new_tokens,
    }
    _gemma_logger.debug("[Gemma-SYNC] Payload keys: %s", list(payload.keys()))

    try:
        _gemma_logger.info(
            "[Gemma-SYNC] → POST %s/infer  (timeout=%ds)",
            _GEMMA_NGROK_URL, _GEMMA_TIMEOUT_SECONDS,
        )
        response = _requests.post(
            f"{_GEMMA_NGROK_URL}/infer",
            json=payload,
            timeout=_GEMMA_TIMEOUT_SECONDS,
        )
        _gemma_logger.info(
            "[Gemma-SYNC] ← HTTP %d from /infer", response.status_code
        )
        response.raise_for_status()
        data = response.json()
        _gemma_logger.info(
            "[Gemma-SYNC] ✔ Response received | json_valid=%s | answer_len=%d",
            data.get("json_valid", "N/A"),
            len(str(data.get("answer", ""))),
        )

        if json_mode and data.get("json_valid"):
            return _json.dumps(data["json_data"], indent=2)
        return data.get("answer", "No answer returned.")

    except _requests.exceptions.ConnectionError as exc:
        _gemma_logger.error("[Gemma-SYNC] ✗ Connection error: %s", exc)
        return "Gemma model unavailable: Colab/ngrok session may have disconnected."
    except _requests.exceptions.Timeout:
        _gemma_logger.error(
            "[Gemma-SYNC] ✗ Timeout after %ds", _GEMMA_TIMEOUT_SECONDS
        )
        return f"Gemma model timed out (>{_GEMMA_TIMEOUT_SECONDS}s). Try a shorter prompt."
    except Exception as exc:
        _gemma_logger.exception("[Gemma-SYNC] ✗ Unexpected error: %s", exc)
        return f"Gemma inference failed: {str(exc)}"


# ------------------------------------------------------------------
# ASYNC helper via aiohttp — native async, keeps event loop free
# ------------------------------------------------------------------
async def get_gemma_insight_async(
    context: str,
    question: str,
    json_mode: bool = False,
    temperature: float = 1.0,
    max_new_tokens: int = 512,
) -> str:
    """
    Async version of get_gemma_insight using native aiohttp.
    Does NOT block the event loop — safe to run alongside other async agents.
    Timeout is set to _GEMMA_TIMEOUT_SECONDS (default 600s) for vLLM.
    """
    _gemma_logger.info(
        "[Gemma-ASYNC] ▶ Starting async inference | url=%s | json_mode=%s | "
        "max_new_tokens=%d | temperature=%.2f",
        _GEMMA_NGROK_URL, json_mode, max_new_tokens, temperature,
    )

    if not _GEMMA_NGROK_URL:
        _gemma_logger.error("[Gemma-ASYNC] ✗ GEMMA_NGROK_URL is not set in .env")
        return "Gemma model unavailable: GEMMA_NGROK_URL not set in .env"

    payload = {
        "context":        context,
        "question":       question,
        "json_mode":      json_mode,
        "temperature":    temperature,
        "max_new_tokens": max_new_tokens,
    }

    timeout = _aiohttp.ClientTimeout(total=_GEMMA_TIMEOUT_SECONDS)
    endpoint = f"{_GEMMA_NGROK_URL}/infer"

    _gemma_logger.info(
        "[Gemma-ASYNC] → POST %s  (timeout=%ds)", endpoint, _GEMMA_TIMEOUT_SECONDS
    )
    try:
        async with _aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                endpoint,
                json=payload,
                headers={"ngrok-skip-browser-warning": "true"},
            ) as resp:
                _gemma_logger.info(
                    "[Gemma-ASYNC] ← HTTP %d from /infer", resp.status
                )
                if resp.status != 200:
                    body = await resp.text()
                    _gemma_logger.error(
                        "[Gemma-ASYNC] ✗ Non-200 response: status=%d body=%s",
                        resp.status, body[:200],
                    )
                    return f"Gemma /infer returned HTTP {resp.status}: {body[:200]}"

                data = await resp.json(content_type=None)
                _gemma_logger.info(
                    "[Gemma-ASYNC] ✔ Response received | json_valid=%s | answer_len=%d",
                    data.get("json_valid", "N/A"),
                    len(str(data.get("answer", ""))),
                )

                if json_mode and data.get("json_valid"):
                    return _json.dumps(data["json_data"], indent=2)
                return data.get("answer", "No answer returned.")

    except _aiohttp.ClientConnectorError as exc:
        _gemma_logger.error("[Gemma-ASYNC] ✗ Connection error: %s", exc)
        return "Gemma model unavailable: Colab/ngrok session may have disconnected."
    except asyncio.TimeoutError:
        _gemma_logger.error(
            "[Gemma-ASYNC] ✗ Timeout after %ds", _GEMMA_TIMEOUT_SECONDS
        )
        return f"Gemma model timed out (>{_GEMMA_TIMEOUT_SECONDS}s). Try a shorter prompt."
    except Exception as exc:
        _gemma_logger.exception("[Gemma-ASYNC] ✗ Unexpected error: %s", exc)
        return f"Gemma async inference failed: {str(exc)}"


# ------------------------------------------------------------------
# vLLM OpenAI-compatible endpoint  (/v1/chat/completions)
# Used by evaluation_agent nodes for structured startup analysis
# ------------------------------------------------------------------
async def get_gemma_vllm_async(
    system_prompt: str,
    user_message: str,
    model_name: str = "google/gemma-3-4b-it",
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> str:
    """
    Calls the vLLM server's OpenAI-compatible /v1/chat/completions endpoint.

    vLLM hosted on Colab + exposed via ngrok serves a standard OpenAI API.
    This is the preferred way for the evaluation_agent nodes to call Gemma,
    as it supports system prompts, chat format, and structured JSON output.

    Args:
        system_prompt: The system instruction (role + task).
        user_message:  The user-facing prompt (formatted startup data).
        model_name:    The model ID as seen by vLLM (check ``/v1/models``).
        temperature:   Sampling temperature (lower = more deterministic).
        max_tokens:    Max tokens to generate.

    Returns:
        str: The assistant's reply text, or an error description.

    Usage in any evaluation node::

        from app.core.llm import get_gemma_vllm_async
        result = await get_gemma_vllm_async(
            system_prompt="You are a startup evaluator...",
            user_message=json.dumps(startup_data),
        )
    """
    _gemma_logger.info(
        "[Gemma-vLLM] ▶ Starting chat/completions call | url=%s | model=%s | "
        "max_tokens=%d | temperature=%.2f",
        _GEMMA_NGROK_URL, model_name, max_tokens, temperature,
    )

    if not _GEMMA_NGROK_URL:
        _gemma_logger.error("[Gemma-vLLM] ✗ GEMMA_NGROK_URL is not set in .env")
        return "Gemma vLLM unavailable: GEMMA_NGROK_URL not set in .env"

    endpoint = f"{_GEMMA_NGROK_URL}/v1/chat/completions"
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        "temperature": temperature,
        "max_tokens":  max_tokens,
    }

    _gemma_logger.debug(
        "[Gemma-vLLM] Payload summary | system_len=%d | user_len=%d",
        len(system_prompt), len(user_message),
    )

    timeout = _aiohttp.ClientTimeout(total=_GEMMA_TIMEOUT_SECONDS)

    _gemma_logger.info(
        "[Gemma-vLLM] → POST %s  (timeout=%ds)", endpoint, _GEMMA_TIMEOUT_SECONDS
    )
    try:
        async with _aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                endpoint,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "ngrok-skip-browser-warning": "true",
                },
            ) as resp:
                _gemma_logger.info(
                    "[Gemma-vLLM] ← HTTP %d from /v1/chat/completions", resp.status
                )
                raw_body = await resp.text()

                if resp.status != 200:
                    _gemma_logger.error(
                        "[Gemma-vLLM] ✗ Non-200 response: status=%d body=%s",
                        resp.status, raw_body[:300],
                    )
                    return (
                        f"Gemma vLLM /v1/chat/completions returned "
                        f"HTTP {resp.status}: {raw_body[:300]}"
                    )

                data = _json.loads(raw_body)
                choices = data.get("choices", [])
                if not choices:
                    _gemma_logger.warning(
                        "[Gemma-vLLM] ⚠ Empty choices in response: %s",
                        raw_body[:200],
                    )
                    return "Gemma vLLM returned empty choices."

                answer = choices[0].get("message", {}).get("content", "")
                usage = data.get("usage", {})
                _gemma_logger.info(
                    "[Gemma-vLLM] ✔ Done | answer_len=%d | prompt_tokens=%s | "
                    "completion_tokens=%s | total_tokens=%s",
                    len(answer),
                    usage.get("prompt_tokens", "?"),
                    usage.get("completion_tokens", "?"),
                    usage.get("total_tokens", "?"),
                )
                return answer

    except _aiohttp.ClientConnectorError as exc:
        _gemma_logger.error("[Gemma-vLLM] ✗ Connection error: %s", exc)
        return "Gemma vLLM unavailable: ngrok/Colab session may have disconnected."
    except asyncio.TimeoutError:
        _gemma_logger.error(
            "[Gemma-vLLM] ✗ Timeout after %ds — vLLM may still be processing.",
            _GEMMA_TIMEOUT_SECONDS,
        )
        return (
            f"Gemma vLLM timed out (>{_GEMMA_TIMEOUT_SECONDS}s). "
            "The model may need more time or the prompt is too large."
        )
    except _json.JSONDecodeError as exc:
        _gemma_logger.error("[Gemma-vLLM] ✗ JSON decode error: %s", exc)
        return f"Gemma vLLM returned invalid JSON: {str(exc)}"
    except Exception as exc:
        _gemma_logger.exception("[Gemma-vLLM] ✗ Unexpected error: %s", exc)
        return f"Gemma vLLM inference failed: {str(exc)}"