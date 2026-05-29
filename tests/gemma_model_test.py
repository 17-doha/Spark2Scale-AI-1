"""
tests/gemma_model_test.py
=========================
Unit tests for the Gemma 3n model integration.

Modules under test
------------------
  app.core.llm.ModalCustomLLM   — LangChain wrapper that calls the Modal /infer endpoint
  app.core.llm.get_llm          — Provider factory (modal / groq / ollama / gemini)

Test isolation strategy
-----------------------
* ALL HTTP calls (requests.post / aiohttp) are mocked — tests run 100% offline.
* No API keys, no GPU, no Modal deployment required.
* The `patch_concurrency_limiter` autouse fixture from conftest.py handles
  the asyncio.Semaphore issue automatically.

Run all Gemma tests:
    pytest tests/gemma_model_test.py -v

Run with coverage:
    pytest tests/gemma_model_test.py -v --cov=app.core.llm --cov-report=term-missing
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Mark every test in this file with 'gemma' so CI can skip them by default
# and run them only when the commit message contains "test-gemma".
pytestmark = pytest.mark.gemma

# ---------------------------------------------------------------------------
# 1. ModalCustomLLM — _split_prompt
# ---------------------------------------------------------------------------

class TestModalCustomLLMSplitPrompt:
    """Tests the internal prompt-splitting convention used by evaluation chains."""

    def _split(self, text: str):
        from app.core.llm import ModalCustomLLM
        return ModalCustomLLM._split_prompt(text)

    def test_splits_on_double_newline(self):
        """Context and question are separated correctly at the first double newline."""
        context, question = self._split("Data block here\n\nScore this startup.")
        assert context == "Data block here"
        assert question == "Score this startup."

    def test_no_separator_yields_empty_context(self):
        """When there is no double newline the whole text becomes the question."""
        context, question = self._split("Just a plain question with no separator.")
        assert context == ""
        assert question == "Just a plain question with no separator."

    def test_only_separator_yields_empty_both(self):
        """Edge-case: prompt is nothing but whitespace / blank lines."""
        context, question = self._split("\n\n")
        assert context == ""
        assert question == ""

    def test_multiple_double_newlines_splits_at_first(self):
        """Only the FIRST double-newline is the separator; the rest stays in question."""
        context, question = self._split("Block A\n\nPart B\n\nPart C")
        assert context == "Block A"
        assert "Part B" in question
        assert "Part C" in question

    def test_strips_surrounding_whitespace(self):
        """Leading/trailing whitespace on each part is stripped."""
        context, question = self._split("  context  \n\n  question  ")
        assert context == "context"
        assert question == "question"


# ---------------------------------------------------------------------------
# 2. ModalCustomLLM — _call (sync)
# ---------------------------------------------------------------------------

class TestModalCustomLLMSyncCall:
    """Tests the synchronous _call method (used by .invoke())."""

    @pytest.fixture
    def llm(self):
        from app.core.llm import ModalCustomLLM
        return ModalCustomLLM(temperature=0.3, max_tokens=512, json_mode=False)

    def _mock_response(self, answer: str, json_valid: bool = False, json_data=None):
        """Build a mock requests.Response whose .json() returns the given payload."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        payload = {"answer": answer}
        if json_valid:
            payload["json_valid"] = True
            payload["json_data"] = json_data
        mock_resp.json.return_value = payload
        return mock_resp

    @patch("app.core.llm.requests.post")
    def test_returns_answer_field(self, mock_post, llm):
        """Normal response: the 'answer' field from the API is returned."""
        mock_post.return_value = self._mock_response("Startup looks promising.")
        result = llm._call("Some context\n\nScore this.")
        assert result == "Startup looks promising."

    @patch("app.core.llm.requests.post")
    def test_posts_correct_payload_fields(self, mock_post, llm):
        """The payload sent to Modal must include all required fields."""
        mock_post.return_value = self._mock_response("ok")
        llm._call("context block\n\nquestion block")

        _, kwargs = mock_post.call_args
        body = kwargs["json"]
        assert "context" in body
        assert "question" in body
        assert "json_mode" in body
        assert "temperature" in body
        assert "max_new_tokens" in body

    @patch("app.core.llm.requests.post")
    def test_payload_splits_prompt_correctly(self, mock_post, llm):
        """Context and question are split and sent in separate payload fields."""
        mock_post.return_value = self._mock_response("ok")
        llm._call("my context\n\nmy question")

        body = mock_post.call_args[1]["json"]
        assert body["context"] == "my context"
        assert body["question"] == "my question"

    @patch("app.core.llm.requests.post")
    def test_json_mode_true_returns_parsed_json_string(self, mock_post, llm):
        """When json_mode=True and json_valid=True, the json_data dict is returned as a string."""
        from app.core.llm import ModalCustomLLM
        json_llm = ModalCustomLLM(json_mode=True)
        mock_post.return_value = self._mock_response(
            "ignored answer",
            json_valid=True,
            json_data={"score": "4/5", "explanation": "Strong team"}
        )
        result = json_llm._call("ctx\n\nq")
        parsed = json.loads(result)
        assert parsed["score"] == "4/5"
        assert parsed["explanation"] == "Strong team"

    @patch("app.core.llm.requests.post")
    def test_json_mode_false_returns_raw_answer(self, mock_post, llm):
        """When json_mode=False, always return the 'answer' field even if json_data exists."""
        mock_post.return_value = self._mock_response(
            "natural language answer",
            json_valid=True,
            json_data={"key": "value"}
        )
        result = llm._call("ctx\n\nq")
        assert result == "natural language answer"

    @patch("app.core.llm.requests.post")
    def test_empty_answer_returns_empty_string(self, mock_post, llm):
        """API returning an empty 'answer' yields an empty string, not an error."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {}
        mock_post.return_value = mock_resp
        result = llm._call("ctx\n\nq")
        assert result == ""

    @patch("app.core.llm.requests.post")
    def test_raises_on_http_error(self, mock_post, llm):
        """HTTP errors propagate as exceptions — not silently swallowed."""
        from requests.exceptions import HTTPError
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = HTTPError("500 Server Error")
        mock_post.return_value = mock_resp

        with pytest.raises(HTTPError):
            llm._call("ctx\n\nq")

    @patch("app.core.llm.requests.post")
    def test_temperature_forwarded_in_payload(self, mock_post, llm):
        """The temperature set on the instance is sent in the request body."""
        mock_post.return_value = self._mock_response("ok")
        llm._call("ctx\n\nq")
        body = mock_post.call_args[1]["json"]
        assert body["temperature"] == pytest.approx(0.3)

    @patch("app.core.llm.requests.post")
    def test_max_tokens_forwarded_in_payload(self, mock_post, llm):
        """The max_tokens set on the instance is sent as max_new_tokens."""
        mock_post.return_value = self._mock_response("ok")
        llm._call("ctx\n\nq")
        body = mock_post.call_args[1]["json"]
        assert body["max_new_tokens"] == 512


# ---------------------------------------------------------------------------
# 3. ModalCustomLLM — _acall (async)
# ---------------------------------------------------------------------------

class TestModalCustomLLMAsyncCall:
    """Tests the asynchronous _acall method (used by .ainvoke())."""

    @pytest.fixture
    def llm(self):
        from app.core.llm import ModalCustomLLM
        return ModalCustomLLM(temperature=0.5, max_tokens=256, json_mode=False)

    def _make_aiohttp_mock(self, payload: dict):
        """Build a mock aiohttp async context-manager chain returning `payload`."""
        mock_resp = AsyncMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = AsyncMock(return_value=payload)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_ctx)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        return mock_session_ctx

    @pytest.mark.asyncio
    @patch("app.core.llm.aiohttp.ClientSession")
    async def test_async_returns_answer(self, mock_session_cls, llm):
        """Async call returns the 'answer' field from the JSON response."""
        mock_session_cls.return_value = self._make_aiohttp_mock(
            {"answer": "Async Gemma response"}
        )
        result = await llm._acall("context\n\nquestion")
        assert result == "Async Gemma response"

    @pytest.mark.asyncio
    @patch("app.core.llm.aiohttp.ClientSession")
    async def test_async_json_mode_returns_parsed_dict_string(self, mock_session_cls):
        """Async call with json_mode=True returns the json_data as a JSON string."""
        from app.core.llm import ModalCustomLLM
        json_llm = ModalCustomLLM(json_mode=True)
        mock_session_cls.return_value = self._make_aiohttp_mock({
            "answer": "ignored",
            "json_valid": True,
            "json_data": {"score": "3/5", "verdict": "Invest"}
        })
        result = await json_llm._acall("ctx\n\nq")
        parsed = json.loads(result)
        assert parsed["score"] == "3/5"
        assert parsed["verdict"] == "Invest"

    @pytest.mark.asyncio
    @patch("app.core.llm.aiohttp.ClientSession")
    async def test_async_empty_answer(self, mock_session_cls, llm):
        """Async call gracefully returns empty string when 'answer' is absent."""
        mock_session_cls.return_value = self._make_aiohttp_mock({})
        result = await llm._acall("ctx\n\nq")
        assert result == ""

    @pytest.mark.asyncio
    @patch("app.core.llm.aiohttp.ClientSession")
    async def test_async_payload_fields(self, mock_session_cls, llm):
        """Async call sends the same required fields as the sync version."""
        captured = {}

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = AsyncMock(return_value={"answer": "ok"})

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        def fake_post(url, **kwargs):
            captured.update(kwargs.get("json", {}))
            return mock_ctx

        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=fake_post)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session_ctx

        await llm._acall("my context\n\nmy question")

        assert captured.get("context") == "my context"
        assert captured.get("question") == "my question"
        assert "json_mode" in captured
        assert "temperature" in captured
        assert "max_new_tokens" in captured


# ---------------------------------------------------------------------------
# 4. ModalCustomLLM — LLM type identity
# ---------------------------------------------------------------------------

class TestModalCustomLLMIdentity:
    """Tests for the LangChain-required _llm_type property."""

    def test_llm_type_is_modal_gemma3n(self):
        """_llm_type must return the registered model identifier."""
        from app.core.llm import ModalCustomLLM
        llm = ModalCustomLLM()
        assert llm._llm_type == "modal_gemma3n"

    def test_default_endpoint_is_modal_url(self):
        """Default endpoint_url points to the Modal deployment."""
        from app.core.llm import ModalCustomLLM
        llm = ModalCustomLLM()
        assert "modal.run" in llm.endpoint_url

    def test_default_json_mode_is_false(self):
        """json_mode defaults to False (conversational / non-structured output)."""
        from app.core.llm import ModalCustomLLM
        llm = ModalCustomLLM()
        assert llm.json_mode is False

    def test_custom_endpoint_url_accepted(self):
        """A custom endpoint URL can override the default."""
        from app.core.llm import ModalCustomLLM
        llm = ModalCustomLLM(endpoint_url="https://custom.example.com/infer")
        assert llm.endpoint_url == "https://custom.example.com/infer"


# ---------------------------------------------------------------------------
# 5. get_llm factory — modal provider
# ---------------------------------------------------------------------------

class TestGetLlmModalProvider:
    """Tests that get_llm('modal') returns a correctly configured ModalCustomLLM."""

    def test_returns_modal_custom_llm_instance(self):
        """get_llm with provider='modal' returns a ModalCustomLLM."""
        from app.core.llm import get_llm, ModalCustomLLM
        llm = get_llm(provider="modal")
        assert isinstance(llm, ModalCustomLLM)

    def test_json_mode_false_by_default(self):
        """Default call produces an LLM with json_mode=False."""
        from app.core.llm import get_llm
        llm = get_llm(provider="modal")
        assert llm.json_mode is False

    def test_json_mode_true_passed_through(self):
        """json_mode=True is forwarded to the ModalCustomLLM instance."""
        from app.core.llm import get_llm
        llm = get_llm(provider="modal", json_mode=True)
        assert llm.json_mode is True

    def test_temperature_passed_through(self):
        """Custom temperature is forwarded to the ModalCustomLLM instance."""
        from app.core.llm import get_llm
        llm = get_llm(provider="modal", temperature=0.1)
        assert llm.temperature == pytest.approx(0.1)

    def test_max_tokens_fixed_at_1024(self):
        """Modal LLM always uses max_tokens=1024 (context budget guard)."""
        from app.core.llm import get_llm
        llm = get_llm(provider="modal")
        assert llm.max_tokens == 1024


# ---------------------------------------------------------------------------
# 6. get_llm factory — other providers (smoke tests)
# ---------------------------------------------------------------------------

class TestGetLlmOtherProviders:
    """Smoke tests to ensure the factory dispatches correctly for non-Modal providers."""

    @patch("app.core.llm.ChatGoogleGenerativeAI")
    def test_gemini_provider(self, mock_gemini):
        """provider='gemini' calls ChatGoogleGenerativeAI."""
        from app.core.llm import get_llm
        from app.core.config import Config
        # Ensure GEMINI_API_KEY is available for the factory
        with patch.object(Config, "GEMINI_API_KEY", "fake-key", create=True):
            get_llm(provider="gemini")
        mock_gemini.assert_called_once()

    @patch("app.core.llm.ChatOllama")
    def test_ollama_provider(self, mock_ollama):
        """provider='ollama' calls ChatOllama."""
        from app.core.llm import get_llm
        get_llm(provider="ollama")
        mock_ollama.assert_called_once()

    @patch("app.core.llm._get_next_groq_key", return_value="fake-groq-key")
    @patch("app.core.llm.ChatGroq")
    def test_groq_provider(self, mock_groq, mock_key):
        """provider='groq' calls ChatGroq with a rotated API key."""
        from app.core.llm import get_llm
        get_llm(provider="groq")
        mock_groq.assert_called_once()


# ---------------------------------------------------------------------------
# 7. ModalCustomLLM — end-to-end LangChain chain integration
# ---------------------------------------------------------------------------

class TestModalLLMChainIntegration:
    """
    Verifies that ModalCustomLLM works correctly when composed in a
    LangChain LCEL chain (prompt | llm | StrOutputParser).
    """

    @patch("app.core.llm.requests.post")
    def test_sync_chain_invoke(self, mock_post):
        """LLM can be piped into a StrOutputParser and invoked synchronously."""
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import StrOutputParser
        from app.core.llm import ModalCustomLLM

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"answer": "Chained Gemma output"}
        mock_post.return_value = mock_resp

        llm = ModalCustomLLM(temperature=0.0, json_mode=False)
        prompt = ChatPromptTemplate.from_messages([("human", "{input}")])
        chain = prompt | llm | StrOutputParser()

        result = chain.invoke({"input": "Evaluate this startup."})
        assert result == "Chained Gemma output"

    @pytest.mark.asyncio
    @patch("app.core.llm.aiohttp.ClientSession")
    async def test_async_chain_ainvoke(self, mock_session_cls):
        """LLM can be piped into a StrOutputParser and invoked asynchronously."""
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import StrOutputParser
        from app.core.llm import ModalCustomLLM

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = AsyncMock(return_value={"answer": "Async chained output"})

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_ctx)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session_ctx

        llm = ModalCustomLLM(temperature=0.0, json_mode=False)
        prompt = ChatPromptTemplate.from_messages([("human", "{input}")])
        chain = prompt | llm | StrOutputParser()

        result = await chain.ainvoke({"input": "Async evaluation request."})
        assert result == "Async chained output"

    @patch("app.core.llm.requests.post")
    def test_json_mode_chain_returns_parseable_json(self, mock_post):
        """JSON-mode chain output can be parsed back into a Python dict."""
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import StrOutputParser
        from app.core.llm import ModalCustomLLM

        expected = {"score": "5/5", "verdict": "Strong Invest"}
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "answer": "ignored",
            "json_valid": True,
            "json_data": expected,
        }
        mock_post.return_value = mock_resp

        llm = ModalCustomLLM(json_mode=True)
        prompt = ChatPromptTemplate.from_messages([("human", "{input}")])
        chain = prompt | llm | StrOutputParser()

        raw = chain.invoke({"input": "Score this startup."})
        parsed = json.loads(raw)
        assert parsed["score"] == "5/5"
        assert parsed["verdict"] == "Strong Invest"


# ---------------------------------------------------------------------------
# 8. ModalCustomLLM — integration test (live Modal endpoint, skipped in CI)
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_modal_gemma_live_endpoint():
    """
    Makes a REAL call to the Modal-deployed Gemma 3n endpoint.

    Requirements:
      - MODAL_INFER_URL env var must resolve to a running Modal deployment.
      - Network access required.

    Skipped automatically unless you pass --run-integration or
    PYTEST_RUN_INTEGRATION=true.

    Run manually:
        pytest tests/gemma_model_test.py::test_modal_gemma_live_endpoint -v -s
    """
    from app.core.llm import ModalCustomLLM

    llm = ModalCustomLLM(temperature=0.1, max_tokens=128, json_mode=False)
    result = await llm._acall(
        "You are an AI. Respond with one sentence.\n\nSay hello to Spark2Scale."
    )

    assert isinstance(result, str), f"Expected str, got {type(result)}"
    assert len(result.strip()) >= 5, f"Response too short: {result!r}"
    print(f"\n[Live Gemma] response: {result}")
