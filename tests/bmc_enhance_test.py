"""
BMC Enhance Agent — Integrated Test Suite
=========================================
Unit tests for the Business Model Canvas refinement endpoint
(`enhance_bmc` in `app/graph/BMC/node.py`).

Sections:
  1. SCHEMA VALIDATION (BMCEnhanceRequest / BMCEnhanceResponse)
  2. ENHANCE_BMC HAPPY PATH
  3. ENHANCE_BMC ERROR PATHS
  4. CHANGE LOG NORMALIZATION
"""

import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app.api.schemas import BMCEnhanceRequest, BMCEnhanceResponse
from app.graph.BMC.node import enhance_bmc


# A minimal, schema-valid current BMC the founder might already have.
def _full_canvas() -> dict:
    return {
        "value_proposition": ["Save 10h/wk per ops manager"],
        "customer_segments": ["SMB ops teams"],
        "revenue_streams": ["$49/seat/mo SaaS"],
        "channels": ["Direct outbound"],
        "customer_relationships": ["Self-serve onboarding"],
        "key_resources": ["Founding eng team"],
        "key_activities": ["Weekly product iteration"],
        "key_partnerships": ["Slack app directory"],
        "cost_structure": ["Cloud hosting $1k/mo"],
    }


# ===========================================================================
# 1. SCHEMA VALIDATION
# ===========================================================================
class TestEnhanceSchemas:
    def test_request_round_trips(self):
        req = BMCEnhanceRequest(
            idea_name="Acme",
            idea_description="AI scheduler",
            region="MENA",
            current_bmc=_full_canvas(),
            document_changes=["Add enterprise tier", "Drop freemium"],
        )
        assert req.idea_name == "Acme"
        assert req.region == "MENA"
        assert len(req.document_changes) == 2

    def test_request_defaults_region_to_global(self):
        req = BMCEnhanceRequest(
            idea_name="Acme",
            idea_description="AI scheduler",
            current_bmc=_full_canvas(),
            document_changes=["x"],
        )
        assert req.region == "Global"

    def test_response_round_trips(self):
        resp = BMCEnhanceResponse(
            message="ok",
            business_model_canvas=_full_canvas(),
            change_log=["value_proposition: tightened wording"],
            errors=[],
        )
        assert resp.message == "ok"
        assert resp.change_log == ["value_proposition: tightened wording"]
        assert resp.errors == []


# ===========================================================================
# 2. ENHANCE_BMC HAPPY PATH
# ===========================================================================
class TestEnhanceBMCHappyPath:
    @pytest.mark.asyncio
    @patch("app.graph.BMC.node.get_llm")
    async def test_enhance_returns_updated_canvas_and_change_log(self, mock_get_llm):
        """With a well-formed LLM response, enhance_bmc returns the new canvas + change_log."""
        new_canvas = _full_canvas()
        new_canvas["value_proposition"] = ["NEW: 12h/wk savings, enterprise SSO"]

        llm_payload = {
            "business_model_canvas": new_canvas,
            "change_log": [
                "value_proposition: added enterprise SSO",
                "customer_segments: unchanged",
            ],
        }
        fake_response = MagicMock()
        fake_response.content = "```json\n" + json.dumps(llm_payload) + "\n```"

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=fake_response)
        mock_get_llm.return_value = mock_llm

        result = await enhance_bmc(
            idea_name="Acme",
            idea_description="AI scheduler",
            region="Global",
            current_bmc=_full_canvas(),
            document_changes=["Pivot to enterprise"],
        )

        assert result["business_model_canvas"]["value_proposition"] == [
            "NEW: 12h/wk savings, enterprise SSO"
        ]
        assert "value_proposition: added enterprise SSO" in result["change_log"]
        assert result["errors"] == []
        mock_llm.ainvoke.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("app.graph.BMC.node.get_llm")
    async def test_enhance_uses_async_invoke(self, mock_get_llm):
        """Verify enhance_bmc calls the async (`ainvoke`) path, not the sync `invoke`."""
        fake_response = MagicMock()
        fake_response.content = json.dumps(
            {"business_model_canvas": _full_canvas(), "change_log": []}
        )

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=fake_response)
        mock_get_llm.return_value = mock_llm

        await enhance_bmc(
            idea_name="x",
            idea_description="y",
            region="Global",
            current_bmc=_full_canvas(),
            document_changes=["z"],
        )

        mock_llm.ainvoke.assert_awaited_once()
        mock_llm.invoke.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.graph.BMC.node.get_llm")
    async def test_enhance_defaults_region_when_blank(self, mock_get_llm):
        """An empty region argument is normalized to 'Global' inside the prompt template."""
        fake_response = MagicMock()
        fake_response.content = json.dumps(
            {"business_model_canvas": _full_canvas(), "change_log": []}
        )

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=fake_response)
        mock_get_llm.return_value = mock_llm

        await enhance_bmc(
            idea_name="x",
            idea_description="y",
            region="",
            current_bmc=_full_canvas(),
            document_changes=["z"],
        )

        # The HumanMessage is positional[1] in the [SystemMessage, HumanMessage] list.
        call_args, _ = mock_llm.ainvoke.await_args
        human_msg = call_args[0][1]
        assert "Global" in human_msg.content


# ===========================================================================
# 3. ENHANCE_BMC ERROR PATHS
# ===========================================================================
class TestEnhanceBMCErrorPaths:
    @pytest.mark.asyncio
    @patch("app.graph.BMC.node.get_llm")
    async def test_enhance_validation_error_returns_none_canvas(self, mock_get_llm):
        """LLM returns JSON whose canvas has wrong types -> validation error captured."""
        # value_proposition must be List[str]; passing a dict triggers ValidationError.
        bad_canvas = {
            "business_model_canvas": {"value_proposition": {"not": "a list"}},
            "change_log": ["nothing"],
        }
        fake_response = MagicMock()
        fake_response.content = json.dumps(bad_canvas)

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=fake_response)
        mock_get_llm.return_value = mock_llm

        result = await enhance_bmc(
            idea_name="x",
            idea_description="y",
            region="Global",
            current_bmc=_full_canvas(),
            document_changes=["z"],
        )

        assert result["business_model_canvas"] is None
        assert result["change_log"] == []
        assert any("schema validation failed" in e for e in result["errors"])

    @pytest.mark.asyncio
    @patch("app.graph.BMC.node.get_llm")
    async def test_enhance_missing_canvas_key_returns_default_canvas(self, mock_get_llm):
        """Missing business_model_canvas key is tolerated — resulting canvas defaults to empty lists."""
        fake_response = MagicMock()
        fake_response.content = '{"change_log": ["nothing changed"]}'

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=fake_response)
        mock_get_llm.return_value = mock_llm

        result = await enhance_bmc(
            idea_name="x",
            idea_description="y",
            region="Global",
            current_bmc=_full_canvas(),
            document_changes=["z"],
        )

        # No exception path — canvas is rebuilt with default empty lists.
        assert result["business_model_canvas"] is not None
        assert result["business_model_canvas"]["value_proposition"] == []
        assert result["change_log"] == ["nothing changed"]
        assert result["errors"] == []

    @pytest.mark.asyncio
    @patch("app.graph.BMC.node.get_llm")
    async def test_enhance_llm_exception_recorded(self, mock_get_llm):
        """If the LLM call raises, errors list is populated and canvas is None."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("rate limit"))
        mock_get_llm.return_value = mock_llm

        result = await enhance_bmc(
            idea_name="x",
            idea_description="y",
            region="Global",
            current_bmc=_full_canvas(),
            document_changes=["z"],
        )

        assert result["business_model_canvas"] is None
        assert result["change_log"] == []
        assert any("BMC enhance failed" in e for e in result["errors"])


# ===========================================================================
# 4. CHANGE LOG NORMALIZATION
# ===========================================================================
class TestEnhanceChangeLog:
    @pytest.mark.asyncio
    @patch("app.graph.BMC.node.get_llm")
    async def test_change_log_coerced_to_string_list(self, mock_get_llm):
        """Non-list change_log values get wrapped into a single-element list of strings."""
        fake_response = MagicMock()
        fake_response.content = json.dumps(
            {
                "business_model_canvas": _full_canvas(),
                # not a list — node should coerce
                "change_log": "single line",
            }
        )
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=fake_response)
        mock_get_llm.return_value = mock_llm

        result = await enhance_bmc(
            idea_name="x",
            idea_description="y",
            region="Global",
            current_bmc=_full_canvas(),
            document_changes=["z"],
        )

        assert result["change_log"] == ["single line"]

    @pytest.mark.asyncio
    @patch("app.graph.BMC.node.get_llm")
    async def test_change_log_missing_defaults_to_empty(self, mock_get_llm):
        """If LLM omits change_log entirely, return [] (not None)."""
        fake_response = MagicMock()
        fake_response.content = json.dumps(
            {"business_model_canvas": _full_canvas()}
        )
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=fake_response)
        mock_get_llm.return_value = mock_llm

        result = await enhance_bmc(
            idea_name="x",
            idea_description="y",
            region="Global",
            current_bmc=_full_canvas(),
            document_changes=["z"],
        )

        assert result["change_log"] == []

    @pytest.mark.asyncio
    @patch("app.graph.BMC.node.get_llm")
    async def test_change_log_entries_stringified(self, mock_get_llm):
        """Non-string change_log entries are coerced via str()."""
        fake_response = MagicMock()
        fake_response.content = json.dumps(
            {
                "business_model_canvas": _full_canvas(),
                "change_log": [{"block": "value_proposition", "edit": "tightened"}, 42],
            }
        )
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=fake_response)
        mock_get_llm.return_value = mock_llm

        result = await enhance_bmc(
            idea_name="x",
            idea_description="y",
            region="Global",
            current_bmc=_full_canvas(),
            document_changes=["z"],
        )

        assert all(isinstance(x, str) for x in result["change_log"])
        assert "42" in result["change_log"]
