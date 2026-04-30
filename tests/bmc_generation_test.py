"""
BMC Generation Agent — Integrated Test Suite
============================================
Unit tests for the Business Model Canvas generation pipeline
(`app/graph/BMC/`).

Sections:
  1. STATE & SCHEMA VALIDATION
  2. CONTEXT EXTRACTION HELPERS
  3. JSON PARSING HELPER
  4. BMC GENERATION NODES
  5. WORKFLOW SHAPE
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from pydantic import ValidationError

# --- Imports from application ---
from app.graph.BMC.state import BMCState
from app.graph.BMC.schema import BMCEnvelope, BusinessModelCanvas
from app.graph.BMC.helpers import (
    extract_bmc_context,
    _coerce_to_dict,
    _slim_evaluation,
    _slim_recommendation,
)
from app.graph.BMC.node import (
    extract_context_node,
    generate_bmc_node,
    _parse_llm_json,
)
from app.graph.BMC.workflow import create_bmc_workflow, bmc_app


# ===========================================================================
# 1. STATE & SCHEMA VALIDATION
# ===========================================================================
class TestBMCState:
    def test_state_initialization(self):
        """BMCState accepts the expected fields."""
        state: BMCState = {
            "idea_name": "Acme AI",
            "idea_description": "AI scheduling assistant",
            "region": "MENA",
            "market_research": {"executive_summary": "summary"},
            "evaluation": {},
            "recommendation": {},
            "errors": [],
        }
        assert state["idea_name"] == "Acme AI"
        assert state["region"] == "MENA"
        assert state["errors"] == []

    def test_business_model_canvas_default_lists(self):
        """All 9 BMC blocks default to empty lists when omitted."""
        bmc = BusinessModelCanvas()
        for block in (
            "value_proposition",
            "customer_segments",
            "revenue_streams",
            "channels",
            "customer_relationships",
            "key_resources",
            "key_activities",
            "key_partnerships",
            "cost_structure",
        ):
            assert getattr(bmc, block) == []

    def test_bmc_envelope_validates_full_canvas(self):
        """BMCEnvelope round-trips a complete canvas."""
        payload = {
            "business_model_canvas": {
                "value_proposition": ["Save 10h/wk per ops manager"],
                "customer_segments": ["SMB ops teams in MENA"],
                "revenue_streams": ["$49/seat/mo SaaS"],
                "channels": ["Direct outbound"],
                "customer_relationships": ["Self-serve onboarding"],
                "key_resources": ["Founding eng team"],
                "key_activities": ["Weekly product iteration"],
                "key_partnerships": ["Slack app directory"],
                "cost_structure": ["Cloud hosting $1k/mo"],
            }
        }
        envelope = BMCEnvelope(**payload)
        assert envelope.business_model_canvas.value_proposition == [
            "Save 10h/wk per ops manager"
        ]

    def test_bmc_envelope_rejects_missing_canvas(self):
        """BMCEnvelope requires business_model_canvas key."""
        with pytest.raises(ValidationError):
            BMCEnvelope()  # type: ignore[call-arg]


# ===========================================================================
# 2. CONTEXT EXTRACTION HELPERS
# ===========================================================================
class TestBMCHelpers:
    def test_coerce_to_dict_handles_none_and_list_and_envelope(self):
        assert _coerce_to_dict(None) == {}
        assert _coerce_to_dict([]) == {}
        assert _coerce_to_dict([{"a": 1}]) == {"a": 1}
        # `data` envelope unwrapping
        assert _coerce_to_dict({"data": {"a": 1}}) == {"a": 1}
        # `items` envelope unwrapping
        assert _coerce_to_dict({"items": [{"a": 1}]}) == {"a": 1}
        assert _coerce_to_dict("not a dict") == {}

    def test_extract_bmc_context_minimal(self):
        """With just idea_name + description we still get a usable context."""
        ctx = extract_bmc_context(
            idea_name="Acme",
            idea_description="ai assistant",
            region="EU",
            market_research={},
        )
        assert ctx["idea_name"] == "Acme"
        assert ctx["idea_description"] == "ai assistant"
        assert ctx["region"] == "EU"
        assert ctx["competitors"] == []
        assert ctx["evaluation"] == {}
        assert ctx["recommendation"] == {}

    def test_extract_bmc_context_caps_competitors_at_8(self):
        """Helper trims competitors list to 8 to keep prompt size bounded."""
        many = [{"Name": f"c{i}"} for i in range(20)]
        ctx = extract_bmc_context(
            idea_name="x",
            idea_description="y",
            region="Global",
            market_research={"competitors": many},
        )
        assert len(ctx["competitors"]) == 8

    def test_extract_bmc_context_pulls_top_level_costs(self):
        """When startup_costs/monthly_fixed_costs are top-level (legacy MR), helper still finds them."""
        ctx = extract_bmc_context(
            idea_name="x",
            idea_description="y",
            region="Global",
            market_research={
                "startup_costs": 50000,
                "monthly_fixed_costs": 4000,
            },
        )
        assert ctx["startup_costs"] == 50000
        assert ctx["monthly_fixed_costs"] == 4000

    def test_extract_bmc_context_unwraps_csharp_data_envelope(self):
        """The C# client double-wraps payloads in {"data": {...}} — helper must unwrap."""
        ctx = extract_bmc_context(
            idea_name="x",
            idea_description="y",
            region="Global",
            market_research={"data": {"executive_summary": "good"}},
        )
        assert ctx["executive_summary"] == "good"

    def test_slim_evaluation_picks_founder_and_investor_fields(self):
        """_slim_evaluation flattens final_report.founder_output / investor_output."""
        ev = {
            "final_report": {
                "founder_output": {
                    "Content": {
                        "Verdict": "Strong",
                        "Weighted Score": 78,
                        "Top 3 Priorities": ["a", "b", "c"],
                    }
                },
                "investor_output": {
                    "Content": {
                        "Deal Breakers": ["No moat"],
                        "Dimension Rationales": [{"team": "ok"}],
                    }
                },
            },
            "team_report": {"explanation": "Strong CTO"},
        }
        slim = _slim_evaluation(ev)
        assert slim["verdict"] == "Strong"
        assert slim["weighted_score"] == 78
        assert slim["top_priorities"] == ["a", "b", "c"]
        assert slim["deal_breakers"] == ["No moat"]
        assert slim["dimension_explanations"]["team"] == "Strong CTO"

    def test_slim_evaluation_empty_input(self):
        assert _slim_evaluation({}) == {}

    def test_slim_recommendation_prefers_refined_statements(self):
        """When refined_statements has a value, _refined_or_raw uses it over insights."""
        rec = {
            "stage": "seed",
            "insights": {
                "company_name": "Acme",
                "problem_statement": "raw problem",
            },
            "refined_statements": {
                "problem_statement": {"recommended": "polished problem"},
            },
        }
        slim = _slim_recommendation(rec)
        assert slim["company_name"] == "Acme"
        assert slim["problem_statement"] == "polished problem"
        assert slim["stage"] == "seed"

    def test_slim_recommendation_falls_back_to_insights(self):
        """When refined_statements has no recommended value, falls back to raw insights."""
        rec = {
            "insights": {"problem_statement": "raw problem"},
            "refined_statements": {},
        }
        slim = _slim_recommendation(rec)
        assert slim["problem_statement"] == "raw problem"


# ===========================================================================
# 3. JSON PARSING HELPER
# ===========================================================================
class TestParseLLMJson:
    def test_strips_json_code_fence(self):
        raw = '```json\n{"a": 1}\n```'
        assert _parse_llm_json(raw) == {"a": 1}

    def test_strips_plain_code_fence(self):
        raw = '```\n{"a": 1}\n```'
        assert _parse_llm_json(raw) == {"a": 1}

    def test_parses_clean_json(self):
        assert _parse_llm_json('{"a": 1}') == {"a": 1}

    def test_repairs_broken_json(self):
        """json_repair fallback handles trailing commas / single quotes."""
        raw = "{'a': 1, 'b': 2,}"
        result = _parse_llm_json(raw)
        assert result == {"a": 1, "b": 2}


# ===========================================================================
# 4. BMC GENERATION NODES
# ===========================================================================
class TestBMCNodes:
    def _base_state(self) -> BMCState:
        return {
            "idea_name": "Acme AI",
            "idea_description": "AI scheduling assistant",
            "region": "Global",
            "market_research": {
                "executive_summary": "Big TAM",
                "competitors": [{"Name": "Calendly"}],
                "finance": {"startup_costs": 50000},
            },
            "evaluation": {},
            "recommendation": {},
            "errors": [],
        }

    def test_extract_context_node_populates_extracted_context(self):
        state = self._base_state()
        out = extract_context_node(state)
        assert "extracted_context" in out
        ctx = out["extracted_context"]
        assert ctx["idea_name"] == "Acme AI"
        assert ctx["region"] == "Global"
        assert len(ctx["competitors"]) == 1

    @patch("app.graph.BMC.node.get_llm")
    def test_generate_bmc_node_happy_path(self, mock_get_llm):
        """generate_bmc_node parses the LLM JSON and returns a canvas."""
        canvas_payload = {
            "business_model_canvas": {
                "value_proposition": ["v1"],
                "customer_segments": ["c1"],
                "revenue_streams": ["r1"],
                "channels": [],
                "customer_relationships": [],
                "key_resources": [],
                "key_activities": [],
                "key_partnerships": [],
                "cost_structure": [],
            }
        }
        fake_response = MagicMock()
        fake_response.content = "```json\n" + json.dumps(canvas_payload) + "\n```"

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = fake_response
        mock_get_llm.return_value = mock_llm

        state = self._base_state()
        state["extracted_context"] = extract_bmc_context(
            idea_name=state["idea_name"],
            idea_description=state["idea_description"],
            region=state["region"],
            market_research=state["market_research"],
        )
        result = generate_bmc_node(state)

        assert result["business_model_canvas"]["value_proposition"] == ["v1"]
        assert result["business_model_canvas"]["customer_segments"] == ["c1"]
        mock_llm.invoke.assert_called_once()

    @patch("app.graph.BMC.node.get_llm")
    def test_generate_bmc_node_validation_error(self, mock_get_llm):
        """When the LLM returns JSON missing the canvas envelope, errors are recorded."""
        fake_response = MagicMock()
        fake_response.content = '{"not_a_canvas": true}'

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = fake_response
        mock_get_llm.return_value = mock_llm

        state = self._base_state()
        state["extracted_context"] = {
            "idea_name": "Acme AI",
            "idea_description": "x",
            "region": "Global",
        }
        result = generate_bmc_node(state)

        assert result["business_model_canvas"] is None
        assert any("schema validation failed" in e for e in result["errors"])

    @patch("app.graph.BMC.node.get_llm")
    def test_generate_bmc_node_llm_exception(self, mock_get_llm):
        """When the LLM call itself raises, the error is appended and canvas is None."""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("boom")
        mock_get_llm.return_value = mock_llm

        state = self._base_state()
        state["extracted_context"] = {
            "idea_name": "x",
            "idea_description": "y",
            "region": "Global",
        }
        result = generate_bmc_node(state)

        assert result["business_model_canvas"] is None
        assert any("BMC generation failed" in e for e in result["errors"])


# ===========================================================================
# 5. WORKFLOW SHAPE
# ===========================================================================
class TestBMCWorkflow:
    def test_module_level_app_compiled(self):
        """`bmc_app` is the compiled workflow imported by the FastAPI route."""
        assert bmc_app is not None
        assert hasattr(bmc_app, "ainvoke")

    def test_create_bmc_workflow_returns_compiled_graph(self):
        wf = create_bmc_workflow()
        assert wf is not None
        assert hasattr(wf, "ainvoke")
