import os
import asyncio

from slowapi import Limiter
from slowapi.util import get_remote_address

# Groq: 4 keys × ~30 RPM free-tier = ~120 RPM total.
# At ~5 s average latency → safe concurrency ceiling ≈ 10.
# Tune via GROQ_CONCURRENT_LIMIT env var.
groq_limiter = asyncio.Semaphore(int(os.getenv("GROQ_CONCURRENT_LIMIT", "8")))

# Modal: serverless GPU (A100), auto-scales its own queue.
# Match vLLM max_num_seqs so extraction tasks never throttle each other.
# Tune via MODAL_CONCURRENT_LIMIT env var.
modal_limiter = asyncio.Semaphore(int(os.getenv("MODAL_CONCURRENT_LIMIT", "32")))

# Backward-compat alias — callers that haven't been updated keep working.
concurrency_limiter = modal_limiter

# Per-IP HTTP rate limiting (slowapi).
DEFAULT_API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "60/minute")
api_limiter = Limiter(key_func=get_remote_address, default_limits=[DEFAULT_API_RATE_LIMIT])
