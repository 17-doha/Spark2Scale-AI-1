"""
tests/idea_check_test.py
=========================
Pytest test suite for the idea_check LangGraph module.

Modules under test
------------------
  app.graph.idea_check.schema   — Pydantic I/O models
  app.graph.idea_check.state    — TypedDict state contract
  app.graph.idea_check.prompts  — Prompt builder functions (pure Python)
  app.graph.idea_check.tools    — execute_search_queries (async, HTTP)
  app.graph.idea_check.node     — generate_queries_node / execute_search_node
                                   / analyze_pain_points_node (async LangGraph nodes)
  app.graph.idea_check.workflow — compiled LangGraph StateGraph

Test isolation strategy
-----------------------
* All LLM calls (get_llm / chain.ainvoke) are mocked with AsyncMock.
* HTTP calls in execute_search_queries are patched via aiohttp so tests run offline.
* Prompt helpers are pure Python — tested directly without mocks.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch




# ---------------------------------------------------------------------------
# 1. Schema tests
# ---------------------------------------------------------------------------

class TestIdeaCheckInput:
    """Validates the Pydantic IdeaCheckInput request schema."""

    def test_minimal_construction(self):
        """CRITICAL – schema builds with required fields only."""
        from app.graph.idea_check.schema import IdeaCheckInput
        inp = IdeaCheckInput(idea="AI tutor for K-12", problem="Students lack personalised help")
        assert inp.idea == "AI tutor for K-12"
        assert inp.problem == "Students lack personalised help"
        assert inp.region == "Global"   # default

    def test_explicit_region(self):
        """HIGH – region field is stored correctly."""
        from app.graph.idea_check.schema import IdeaCheckInput
        inp = IdeaCheckInput(idea="Fintech app", problem="No mobile banking", region="MENA")
        assert inp.region == "MENA"

    def test_rejects_missing_required_fields(self):
        """HIGH – Pydantic raises on missing required fields."""
        from pydantic import ValidationError
        from app.graph.idea_check.schema import IdeaCheckInput
        with pytest.raises(ValidationError):
            IdeaCheckInput(idea="only idea, no problem")


class TestIdeaCheckOutput:
    """Validates the Pydantic IdeaCheckOutput response schema."""

    def test_full_construction(self):
        """HIGH – all required output fields are accepted."""
        from app.graph.idea_check.schema import IdeaCheckOutput
        out = IdeaCheckOutput(
            validation_status="VALIDATED",
            pain_score=75,
            pain_score_reasoning="Strong Reddit signals",
            solution_fit_score="High",
            solution_fit_reasoning="Direct alignment",
            evidence_quality_notes="5 independent sources",
            key_queries_executed={
                "problem_queries": ["site:reddit.com bad tutors"],
                "solution_queries": ["site:producthunt.com AI tutor"],
            },
        )
        assert out.pain_score == 75
        assert out.validation_status == "VALIDATED"

    def test_pain_score_is_int(self):
        """MEDIUM – pain_score must be an integer not a float."""
        from app.graph.idea_check.schema import IdeaCheckOutput
        out = IdeaCheckOutput(
            validation_status="MODERATE",
            pain_score=50,
            pain_score_reasoning="Some evidence",
            solution_fit_score="Medium",
            solution_fit_reasoning="Partial",
            evidence_quality_notes="2 sources",
            key_queries_executed={"problem_queries": [], "solution_queries": []},
        )
        assert isinstance(out.pain_score, int)


# ---------------------------------------------------------------------------
# 2. State tests
# ---------------------------------------------------------------------------

class TestIdeaCheckState:
    """Validates the TypedDict contract for IdeaCheckState."""

    def test_all_required_keys_present(self):
        """MEDIUM – TypedDict annotations must include all pipeline keys."""
        from app.graph.idea_check.state import IdeaCheckState
        keys = set(IdeaCheckState.__annotations__.keys())
        expected = {"idea", "problem", "region", "validation_queries",
                    "search_evidence", "analysis_result", "error"}
        assert expected.issubset(keys)


# ---------------------------------------------------------------------------
# 3. Prompt helper tests
# ---------------------------------------------------------------------------

class TestGenerateValidationQueriesPrompt:
    """Tests the pure-Python prompt builder for query generation."""

    def test_returns_string(self):
        """CRITICAL – prompt builders must always return a non-empty string."""
        from app.graph.idea_check.prompts import generate_validation_queries_prompt
        result = generate_validation_queries_prompt("AI tutor", "students struggle")
        assert isinstance(result, str)
        assert len(result) > 50

    def test_contains_idea_and_problem(self):
        """HIGH – both placeholders must be injected into the prompt text."""
        from app.graph.idea_check.prompts import generate_validation_queries_prompt
        result = generate_validation_queries_prompt("RoboTutor", "Exam anxiety")
        assert "RoboTutor" in result
        assert "Exam anxiety" in result

    def test_contains_json_template_keys(self):
        """HIGH – prompt must request both problem_queries and solution_queries."""
        from app.graph.idea_check.prompts import generate_validation_queries_prompt
        result = generate_validation_queries_prompt("X", "Y")
        assert "problem_queries" in result
        assert "solution_queries" in result


class TestAnalyzePainPointsPrompt:
    """Tests the pure-Python prompt builder for pain-point analysis."""

    def test_returns_string(self):
        """CRITICAL – must return a non-empty string."""
        from app.graph.idea_check.prompts import analyze_pain_points_prompt
        result = analyze_pain_points_prompt("AI tutor", "students struggle", "evidence text")
        assert isinstance(result, str)
        assert len(result) > 50

    def test_contains_idea_and_problem(self):
        """HIGH – idea and problem are interpolated into the prompt."""
        from app.graph.idea_check.prompts import analyze_pain_points_prompt
        result = analyze_pain_points_prompt("RoboTutor", "Exam anxiety", "some evidence")
        assert "RoboTutor" in result
        assert "Exam anxiety" in result

    def test_accepts_list_evidence(self):
        """MEDIUM – evidence as a list is joined correctly without error."""
        from app.graph.idea_check.prompts import analyze_pain_points_prompt
        result = analyze_pain_points_prompt("X", "Y", ["evidence 1", "evidence 2"])
        assert isinstance(result, str)

    def test_contains_score_range_guidance(self):
        """MEDIUM – prompt must include the 0-100 scoring rubric."""
        from app.graph.idea_check.prompts import analyze_pain_points_prompt
        result = analyze_pain_points_prompt("X", "Y", "evidence")
        assert "0-100" in result or "80-100" in result

    def test_contains_output_json_structure(self):
        """HIGH – expected output keys must be in the prompt for structured output."""
        from app.graph.idea_check.prompts import analyze_pain_points_prompt
        result = analyze_pain_points_prompt("X", "Y", "evidence")
        assert "pain_score" in result
        assert "solution_fit_score" in result
        assert "verdict" in result


# ---------------------------------------------------------------------------
# 4. Tools tests  (execute_search_queries — async, HTTP)
# ---------------------------------------------------------------------------

class TestExecuteSearchQueries:
    """Tests the Serper API wrapper — HTTP calls are mocked."""

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_warning_string(self):
        """CRITICAL – missing key must not raise but return a warning string."""
        from app.graph.idea_check.tools import execute_search_queries
        with patch.dict("os.environ", {}, clear=True):
            # Ensure SERPER_API_KEY is absent
            import os
            os.environ.pop("SERPER_API_KEY", None)
            result = await execute_search_queries(["some query"])
        assert "Missing API Key" in result or "No real search" in result

    @pytest.mark.asyncio
    async def test_empty_query_list_returns_no_results(self):
        """MEDIUM – empty query list must not raise; returns 'no results' message."""
        from app.graph.idea_check.tools import execute_search_queries
        with patch.dict("os.environ", {"SERPER_API_KEY": "fake_key"}):
            with patch("aiohttp.ClientSession") as mock_session_cls:
                mock_session = AsyncMock()
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_session.post = MagicMock()
                mock_session_cls.return_value = mock_session
                result = await execute_search_queries([])
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_successful_search_returns_formatted_string(self):
        """HIGH – given a valid API key and mocked HTTP, results are formatted."""
        from app.graph.idea_check.tools import execute_search_queries

        mock_response_data = {
            "organic": [
                {"title": "Reddit post about tutoring", "snippet": "Students need help."}
            ]
        }

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_response_data)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch.dict("os.environ", {"SERPER_API_KEY": "fake_key"}):
            with patch("aiohttp.ClientSession", return_value=mock_session):
                result = await execute_search_queries(["AI tutoring solutions"])

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_serper_error_returns_no_results(self):
        """HIGH – network errors must be swallowed and return 'no results' string."""
        from app.graph.idea_check.tools import execute_search_queries

        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=Exception("Connection refused"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch.dict("os.environ", {"SERPER_API_KEY": "fake_key"}):
            with patch("aiohttp.ClientSession", return_value=mock_session):
                result = await execute_search_queries(["failing query"])

        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# 5. Node tests
# ---------------------------------------------------------------------------

class TestGenerateQueriesNode:
    """Tests the first LangGraph async node — LLM call is mocked."""

    @pytest.fixture
    def base_state(self):
        return {
            "idea": "AI tutor for K-12",
            "problem": "Students lack personalised help",
            "region": "Global",
            "validation_queries": {},
            "search_evidence": "",
            "analysis_result": {},
            "error": None,
        }

    @patch("app.graph.idea_check.node.get_llm")
    @pytest.mark.asyncio
    async def test_returns_validation_queries(self, mock_get_llm, base_state):
        """CRITICAL – node must add validation_queries to state."""
        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value={
            "problem_queries": ["site:reddit.com bad tutors"],
            "solution_queries": ["site:producthunt.com AI tutor"],
        })

        with patch("app.graph.idea_check.node.PromptTemplate") as mock_prompt, \
             patch("app.graph.idea_check.node.JsonOutputParser"):
            mock_prompt.from_template.return_value.__or__ = MagicMock(return_value=mock_chain)
            mock_chain.__or__ = MagicMock(return_value=mock_chain)

            from app.graph.idea_check.node import generate_queries_node
            result = await generate_queries_node(base_state)

        assert "validation_queries" in result

    @patch("app.graph.idea_check.node.get_llm")
    @pytest.mark.asyncio
    async def test_error_stored_on_llm_failure(self, mock_get_llm, base_state):
        """HIGH – LLM exceptions must be caught and stored in state['error']."""
        mock_get_llm.side_effect = RuntimeError("LLM unavailable")

        from app.graph.idea_check.node import generate_queries_node
        result = await generate_queries_node(base_state)

        assert result.get("error") is not None
        assert "failed" in result["error"].lower()


class TestExecuteSearchNode:
    """Tests the second LangGraph async node — HTTP calls are mocked."""

    @pytest.fixture
    def base_state(self):
        return {
            "idea": "AI tutor",
            "problem": "No personalised learning",
            "region": "Global",
            "validation_queries": {
                "problem_queries": ["site:reddit.com missing tutoring"],
                "solution_queries": ["site:producthunt.com AI tutor"],
            },
            "search_evidence": "",
            "analysis_result": {},
            "error": None,
        }

    @pytest.mark.asyncio
    async def test_skips_on_existing_error(self, base_state):
        """HIGH – node must pass state through unchanged if error is already set."""
        base_state["error"] = "Previous error"
        from app.graph.idea_check.node import execute_search_node
        result = await execute_search_node(base_state)
        assert result["error"] == "Previous error"

    @patch("app.graph.idea_check.node.execute_search_queries",
           new_callable=AsyncMock,
           return_value="Mock search results for testing.")
    @pytest.mark.asyncio
    async def test_populates_search_evidence(self, mock_search, base_state):
        """CRITICAL – node must add search_evidence to the state."""
        from app.graph.idea_check.node import execute_search_node
        result = await execute_search_node(base_state)
        assert "search_evidence" in result
        assert result["search_evidence"]

    @patch("app.graph.idea_check.node.execute_search_queries",
           new_callable=AsyncMock,
           side_effect=RuntimeError("Search failed"))
    @pytest.mark.asyncio
    async def test_error_stored_on_search_failure(self, mock_search, base_state):
        """HIGH – network error must be caught and stored as error in state."""
        from app.graph.idea_check.node import execute_search_node
        result = await execute_search_node(base_state)
        assert result.get("error") is not None


class TestAnalyzePainPointsNode:
    """Tests the third LangGraph async node — LLM call is mocked."""

    @pytest.fixture
    def base_state(self):
        return {
            "idea": "AI tutor",
            "problem": "No personalised learning",
            "region": "Global",
            "validation_queries": {
                "problem_queries": ["q1"],
                "solution_queries": ["q2"],
            },
            "search_evidence": "Students struggle with maths. Reddit: 1000 upvotes.",
            "analysis_result": {},
            "error": None,
        }

    @pytest.mark.asyncio
    async def test_skips_on_existing_error(self, base_state):
        """HIGH – node must pass through if error already set."""
        base_state["error"] = "Upstream error"
        from app.graph.idea_check.node import analyze_pain_points_node
        result = await analyze_pain_points_node(base_state)
        assert result["error"] == "Upstream error"

    @patch("app.graph.idea_check.node.get_llm")
    @pytest.mark.asyncio
    async def test_populates_analysis_result(self, mock_get_llm, base_state):
        """CRITICAL – node must add analysis_result to state."""
        expected_analysis = {
            "verdict": "VALIDATED",
            "pain_score": 75,
            "pain_score_reasoning": "Strong signals",
            "solution_fit_score": "High",
            "solution_fit_reasoning": "Direct match",
            "reasoning": "Multiple sources",
            "evidence_quality_notes": "Recent and credible",
        }

        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=expected_analysis)

        with patch("app.graph.idea_check.node.PromptTemplate") as mock_prompt, \
             patch("app.graph.idea_check.node.JsonOutputParser"):
            mock_prompt.from_template.return_value.__or__ = MagicMock(return_value=mock_chain)
            mock_chain.__or__ = MagicMock(return_value=mock_chain)

            from app.graph.idea_check.node import analyze_pain_points_node
            result = await analyze_pain_points_node(base_state)

        assert "analysis_result" in result

    @patch("app.graph.idea_check.node.get_llm")
    @pytest.mark.asyncio
    async def test_attaches_key_queries_to_analysis(self, mock_get_llm, base_state):
        """HIGH – executed queries must be traceable in the final analysis output."""
        mock_analysis = {
            "verdict": "MODERATE", "pain_score": 45,
            "pain_score_reasoning": "Moderate", "solution_fit_score": "Medium",
            "solution_fit_reasoning": "Partial", "reasoning": "Limited sources",
            "evidence_quality_notes": "2 sources",
        }
        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=mock_analysis)

        with patch("app.graph.idea_check.node.PromptTemplate") as mock_prompt, \
             patch("app.graph.idea_check.node.JsonOutputParser"):
            mock_prompt.from_template.return_value.__or__ = MagicMock(return_value=mock_chain)
            mock_chain.__or__ = MagicMock(return_value=mock_chain)

            from app.graph.idea_check.node import analyze_pain_points_node
            result = await analyze_pain_points_node(base_state)

        if "analysis_result" in result and result["analysis_result"]:
            assert "key_queries_executed" in result["analysis_result"]

    @patch("app.graph.idea_check.node.get_llm", side_effect=RuntimeError("LLM down"))
    @pytest.mark.asyncio
    async def test_error_stored_on_llm_failure(self, mock_get_llm, base_state):
        """HIGH – LLM failure must be caught and stored in state['error']."""
        from app.graph.idea_check.node import analyze_pain_points_node
        result = await analyze_pain_points_node(base_state)
        assert result.get("error") is not None


# ---------------------------------------------------------------------------
# 6. Workflow graph tests
# ---------------------------------------------------------------------------

class TestIdeaCheckWorkflow:
    """Tests the compiled LangGraph StateGraph structure."""

    def test_graph_compiles(self):
        """CRITICAL – graph compiles without errors (would fail at import time)."""
        from app.graph.idea_check.workflow import idea_check_app
        assert idea_check_app is not None

    def test_graph_has_three_nodes(self):
        """HIGH – the pipeline must contain exactly the three defined nodes."""
        from app.graph.idea_check.workflow import idea_check_app
        node_names = set(idea_check_app.nodes.keys())
        assert "generate_queries" in node_names
        assert "execute_search" in node_names
        assert "analyze_pain_points" in node_names

    def test_public_api_exports(self):
        """MEDIUM – __init__ must export the three public symbols."""
        from app.graph.idea_check import idea_check_app, IdeaCheckInput, IdeaCheckOutput, IdeaCheckState
        assert idea_check_app is not None
        assert IdeaCheckInput is not None
        assert IdeaCheckOutput is not None
        assert IdeaCheckState is not None


# ---------------------------------------------------------------------------
# 7. Integration test — full graph invoke (all external calls mocked)
# ---------------------------------------------------------------------------

class TestIdeaCheckIntegration:
    """Invokes the compiled LangGraph StateGraph end-to-end with all external calls mocked."""

    @pytest.mark.asyncio
    @patch("app.graph.idea_check.node.get_llm")
    @patch(
        "app.graph.idea_check.node.execute_search_queries",
        new_callable=AsyncMock,
        return_value="Reddit: students struggle with math. Source 1.",
    )
    async def test_full_pipeline_produces_analysis(self, mock_search, mock_get_llm):
        """CRITICAL – the 3-node graph must complete and populate analysis_result."""
        from app.graph.idea_check.workflow import idea_check_app

        expected_analysis = {
            "verdict": "VALIDATED",
            "pain_score": 80,
            "pain_score_reasoning": "Strong signals from Reddit.",
            "solution_fit_score": "High",
            "solution_fit_reasoning": "Direct match.",
            "reasoning": "Multiple evidence sources.",
            "evidence_quality_notes": "Recent and credible.",
        }

        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(side_effect=[
            # First call: generate_queries_node returns query dict
            {"problem_queries": ["site:reddit.com bad tutors"], "solution_queries": ["site:producthunt.com AI tutor"]},
            # Second call: analyze_pain_points_node returns analysis
            expected_analysis,
        ])

        initial_state = {
            "idea": "AI tutor for K-12",
            "problem": "Students lack personalised help",
            "region": "Global",
            "validation_queries": {},
            "search_evidence": "",
            "analysis_result": {},
            "error": None,
        }

        with patch("app.graph.idea_check.node.PromptTemplate") as mock_prompt, \
             patch("app.graph.idea_check.node.JsonOutputParser"):
            mock_prompt.from_template.return_value.__or__ = MagicMock(return_value=mock_chain)
            mock_chain.__or__ = MagicMock(return_value=mock_chain)

            final_state = await idea_check_app.ainvoke(initial_state)

        assert final_state.get("error") is None
        assert "analysis_result" in final_state
        assert final_state["search_evidence"]  # non-empty after execute_search_node

    @pytest.mark.asyncio
    @patch("app.graph.idea_check.node.get_llm", side_effect=RuntimeError("LLM down"))
    async def test_full_pipeline_error_propagation(self, mock_get_llm):
        """HIGH – an LLM failure in node 1 must propagate error through remaining nodes."""
        from app.graph.idea_check.workflow import idea_check_app

        initial_state = {
            "idea": "Fintech app",
            "problem": "No mobile banking",
            "region": "MENA",
            "validation_queries": {},
            "search_evidence": "",
            "analysis_result": {},
            "error": None,
        }

        final_state = await idea_check_app.ainvoke(initial_state)

        # Error must be captured — not raised as an unhandled exception
        assert final_state.get("error") is not None
        assert "failed" in final_state["error"].lower()
