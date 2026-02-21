import asyncio

# Allow 2 concurrent LLM calls — safe with 4 rotating API keys (~120 RPM total)
concurrency_limiter = asyncio.Semaphore(2)
