"""
t5_model_test.py
================
Integration tests for the fine-tuned T5-3B model served on Hugging Face Spaces
via Gradio (Dohahemdann/Spark2Scale-Space).

These tests make a LIVE network call to the HF Space and require:
  - HF_TOKEN set in the project .env file
  - The Gradio Space to be running (may cold-start on first call)

Run from the project root (venv activated):
    pytest tests/t5_model_test.py -v -s

Mark:
    @pytest.mark.integration  — skipped in CI unless --run-integration flag passed.
"""

import time
import asyncio
import pytest
from dotenv import load_dotenv

# .env MUST be loaded before app.core.llm is imported
# (it reads HF_TOKEN at module level inside _get_t5_client)
load_dotenv()

from app.core.llm import get_t5_insight  # noqa: E402 (after dotenv load)


# ---------------------------------------------------------------------------
# Shared test prompt
# ---------------------------------------------------------------------------
_SAMPLE_PROMPT = (
    "Evaluate the following startup context: "
    "Company: Spark2Scale, Stage: Pre-Seed. "
    "Problem: Early-stage founders lack a structured system to validate "
    "ideas and reach investors."
)

# Maximum acceptable latency the test will TOLERATE before failing.
# The assertion checks that the call finished WITHIN this budget.
_MAX_LATENCY_SECONDS = 25


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_t5_model_latency():
    """
    T5 model round-trip must complete within the latency budget.

    The model is hosted on HuggingFace Spaces.  Cold-start can add a few
    seconds, but a warmed Space should respond well under 25 s.
    The test records actual elapsed time and FAILS if it exceeds the budget,
    giving a clear message with the measured value.
    """
    start = time.perf_counter()
    result = await get_t5_insight(_SAMPLE_PROMPT)
    elapsed = time.perf_counter() - start

    print(f"\n⏱  T5 latency: {elapsed:.2f}s (budget: {_MAX_LATENCY_SECONDS}s)")
    print(f"📤 Result: {result[:200]}{'...' if len(result) > 200 else ''}")

    assert elapsed <= _MAX_LATENCY_SECONDS, (
        f"T5 model exceeded latency budget: {elapsed:.2f}s > {_MAX_LATENCY_SECONDS}s"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_t5_model_returns_answer():
    """
    T5 model must return a non-empty, non-error string.

    Verifies that:
    - The result is a string (not None, not a dict, not an exception)
    - The result has at least 10 characters (not just whitespace / empty)
    - The result does NOT start with a known failure prefix
      (e.g. 'T5 Model unavailable' or 'T5 Insight failed')
    """
    result = await get_t5_insight(_SAMPLE_PROMPT)

    print(f"\n📥 Full T5 answer:\n{result}")

    assert isinstance(result, str), f"Expected str, got {type(result)}"
    assert len(result.strip()) >= 10, "T5 returned an empty or near-empty response"
    assert not result.startswith("T5 Model unavailable"), (
        "T5 client could not connect – check HF_TOKEN and Space status"
    )
    assert not result.startswith("T5 Insight failed"), (
        f"T5 call raised an exception: {result}"
    )
