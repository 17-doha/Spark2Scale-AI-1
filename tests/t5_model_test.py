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
from unittest.mock import patch, AsyncMock, MagicMock

from app.graph.evaluation_agent.helpers import get_market_signals_serper
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


@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.helpers.os.environ.get")
@patch("app.graph.evaluation_agent.helpers.aiohttp.ClientSession.post")
async def test_get_market_signals_serper(mock_post, mock_env):
    """Test async Serper market signals fetching."""
    mock_env.return_value = "fake_api_key"
    
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "organic": [{"title": "Report", "snippet": "Market is booming."}]
    }
    mock_post.return_value.__aenter__.return_value = mock_response
    
    vision_data = {"category_play": {"definition": "AI SaaS"}}
    result = await get_market_signals_serper(vision_data)
    
    assert "SOURCE" in result
    assert "Market is booming." in result


# ==========================================
# T5-3B MODEL WRAPPER TESTS
# ==========================================

@pytest.mark.asyncio
@patch("app.core.llm._get_t5_client")
async def test_fetch_t5_deep_insight_success(mock_get_client):
    """T5 wrapper returns model output when client is available."""
    from unittest.mock import MagicMock
    mock_client = MagicMock()
    mock_client.predict.return_value = "Strong team, clear problem, good traction."
    mock_get_client.return_value = mock_client

    user_data = {
        "startup_evaluation": {
            "company_snapshot": {"company_name": "TestCo", "current_stage": "Pre-Seed"},
            "problem_definition": {"problem_statement": "Manual QA is slow."}
        }
    }

    from app.graph.evaluation_agent.helpers import fetch_t5_deep_insight
    result = await fetch_t5_deep_insight(user_data)

    assert result == "Strong team, clear problem, good traction."
    mock_client.predict.assert_called_once()
    call_kwargs = mock_client.predict.call_args.kwargs
    assert "TestCo" in call_kwargs["startup_idea"]
    assert call_kwargs["api_name"] == "/evaluate_idea"


@pytest.mark.asyncio
@patch("app.core.llm._get_t5_client", return_value=None)
async def test_fetch_t5_deep_insight_no_client(mock_get_client):
    """T5 wrapper returns a safe fallback when the client cannot be created."""
    from app.graph.evaluation_agent.helpers import fetch_t5_deep_insight
    result = await fetch_t5_deep_insight({})
    assert "unavailable" in result.lower()

