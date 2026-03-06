import os
import asyncio

from slowapi import Limiter
from slowapi.util import get_remote_address

# Allow 2 concurrent LLM calls — safe with 4 rotating API keys (~120 RPM total)
concurrency_limiter = asyncio.Semaphore(2)

# Rate limiter for incoming HTTP requests (per-IP by default).
# Configure the default rate limit via the API_RATE_LIMIT env var (e.g. "60/minute").
DEFAULT_API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "60/minute")
api_limiter = Limiter(key_func=get_remote_address, default_limits=[DEFAULT_API_RATE_LIMIT])
