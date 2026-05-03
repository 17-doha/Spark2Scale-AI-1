import os
import asyncio

from slowapi import Limiter
from slowapi.util import get_remote_address

# Match vLLM's max_num_seqs=32 so all evaluation-agent calls (36 total) hit
# the GPU in one continuous batch instead of being throttled into waves.
# vLLM's AsyncLLMEngine handles the queuing internally — flooding it is fine.
concurrency_limiter = asyncio.Semaphore(32)

# Rate limiter for incoming HTTP requests (per-IP by default).
# Configure the default rate limit via the API_RATE_LIMIT env var (e.g. "60/minute").
DEFAULT_API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "60/minute")
api_limiter = Limiter(key_func=get_remote_address, default_limits=[DEFAULT_API_RATE_LIMIT])
