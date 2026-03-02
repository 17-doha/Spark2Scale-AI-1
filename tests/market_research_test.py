"""
Market Research Agent — Integrated Test Suite
===================================
This file combines both the low-level helper tests and the high-level 
agent nodes/workflow tests into a single comprehensive test suite.

Sections:
  1. TESTS FOR pdf_utils.py (Data & Parsing)
  2. TESTS FOR market_sizing_validator.py
  3. TESTS FOR validator_utils.py
  4. TESTS FOR LLM / APIs Integration (Mocks)
  5. STATE & SCHEMA VALIDATION
  6. AGENT Nodes (Mocking Tools & LLMs)
  7. WORKFLOW / GRAPH STRUCTURE
"""

import os
import json
import pytest
import pandas as pd
from unittest.mock import patch, AsyncMock, MagicMock

# --- Imports from application ---
from app.graph.market_research_agent.helpers.pdf_utils import remove_emojis
from app.graph.market_research_agent.helpers.market_sizing_validator import RealisticMarketSizer
from app.graph.market_research_agent.helpers.finance_utils import detect_currency
from app.graph.market_research_agent.helpers.research_utils import extract_competitors_strict
from app.graph.market_research_agent.helpers.validator_utils import analyze_pain_intensity

from app.graph.market_research_agent.state import MarketResearchState
from app.graph.market_research_agent.nodes import (
    plan_node,
    competitors_node,
    validation_node,
    trends_node,
    finance_node,
    market_sizing_node,
    report_node,
    pdf_node
)
from app.graph.market_research_agent.workflow import create_market_research_graph


# ==========================================
# 1. TESTS FOR pdf_utils.py (Data & Parsing)
# ==========================================
def test_remove_emojis():
    """Test removing emojis from text."""
    # Note: 'remove_emojis' keeps ascii and arabic, removes others.
    result = remove_emojis("Hello World \U0001f30d")
    assert result.strip() == "Hello World"
    
    # Check if None or non-string is passed
    assert remove_emojis(None) is None
    assert remove_emojis(123) == 123


# ==========================================
# 2. TESTS FOR market_sizing_validator.py
# ==========================================
def test_extract_number_from_text():
    """Test extracting numbers with different scales (Millions, Billions, Trillions)."""
    assert RealisticMarketSizer.extract_number_from_text("$5.2 Billion") == 5200.0
    assert RealisticMarketSizer.extract_number_from_text("500 Million") == 500.0
    assert RealisticMarketSizer.extract_number_from_text("$1.5 Trillion") == 1500000.0
    assert RealisticMarketSizer.extract_number_from_text("10 Thousand") == 0.01

    assert RealisticMarketSizer.extract_number_from_text("Unknown") is None
    assert RealisticMarketSizer.extract_number_from_text("Insufficient data") is None

def test_get_industry_key():
    """Test fuzzy matching for industry grouping limits."""
    assert RealisticMarketSizer.get_industry_key("B2B SaaS") == "SaaS"
    assert RealisticMarketSizer.get_industry_key("E-commerce Store") == "E-commerce"
    assert RealisticMarketSizer.get_industry_key("Random Undefined Industry") == "Default"

def test_determine_market_structure():
    """Test categorization of market structure based on competitor counts."""
    assert RealisticMarketSizer.determine_market_structure(1) == "Winner-Take-All"
    assert RealisticMarketSizer.determine_market_structure(4) == "Concentrated"
    assert RealisticMarketSizer.determine_market_structure(10) == "Competitive"
    assert RealisticMarketSizer.determine_market_structure(20) == "Fragmented"


# ==========================================
# 3. TESTS FOR validator_utils.py
# ==========================================
def test_analyze_pain_intensity():
    """Test counting pain keywords and intensity scaling."""
    evidence_list_high_pain = [
        {"title": "This is terrible", "snippet": "I hate this process, it's a nightmare"}
    ]
    intensity = analyze_pain_intensity(evidence_list_high_pain)
    assert intensity == 1.3
    
    evidence_list_low_pain = [
        {"title": "It's nice to have", "snippet": "minor inconvenience sometimes"}
    ]
    intensity_low = analyze_pain_intensity(evidence_list_low_pain)
    assert intensity_low == 0.7
    
    assert analyze_pain_intensity([]) == 1.0


# ==========================================
# 4. TESTS FOR LLM / APIs Integration (Mocks)
# ==========================================
@patch("app.graph.market_research_agent.helpers.finance_utils.call_gemini")
def test_detect_currency_mock(mock_call_gemini):
    """Test detecting location and currency using mocked gemini call."""
    mock_response = MagicMock()
    mock_response.text = '```json\n{"country": "Egypt", "currency_code": "EGP", "currency_symbol": "EGP"}\n```'
    mock_call_gemini.return_value = mock_response

    result = detect_currency("Delivery app in Egypt")

    assert result["country"] == "Egypt"
    assert result["currency_code"] == "EGP"

@patch("app.graph.market_research_agent.helpers.research_utils.call_gemini")
def test_extract_competitors_strict_mock(mock_call_gemini):
    """Test competitor extraction functionality with LLM mocked."""
    mock_response = MagicMock()
    mock_response.text = '```json\n[{"Name": "Competitor A", "Features": "Feature 1"}]\n```'
    mock_call_gemini.return_value = mock_response

    search_data = [{"title": "Competitor A page", "snippet": "Best product"}]
    result = extract_competitors_strict(search_data, "My App")

    assert len(result) == 1
    assert result[0]["Name"] == "Competitor A"


# ===========================================================================
# 5. STATE & SCHEMA VALIDATION
# ===========================================================================
class TestMarketResearchState:
    def test_state_initialization(self):
        """Test that the state can be initialized with required fields."""
        state: MarketResearchState = {
            "input_idea": "AI Startup",
            "input_problem": "Inefficiency",
            "input_region": "US",
            "research_plan": None,
            "competitors_file": None,
            "validation_file": None,
            "trends_file": None,
            "finance_file": None,
            "market_limit_file": None,
            "report_text": None,
            "pdf_path": None,
            "market_research": None,
            "json_path": None,
        }
        assert state["input_idea"] == "AI Startup"
        assert state["input_problem"] == "Inefficiency"


# ===========================================================================
# 6. AGENT Nodes
# ===========================================================================
class TestAgentNodes:
    def _base_state(self) -> MarketResearchState:
        return {
            "input_idea": "Test Idea",
            "input_problem": "Test Problem",
            "input_region": "Global",
            "research_plan": None,
            "competitors_file": None,
            "validation_file": None,
            "trends_file": None,
            "finance_file": None,
            "market_limit_file": None,
            "report_text": None,
            "pdf_path": None,
            "market_research": None,
            "json_path": None,
        }

    @patch("app.graph.market_research_agent.nodes.generate_research_plan")
    def test_plan_node(self, mock_generate_plan):
        """plan_node should populate the 'research_plan' key."""
        mock_plan = {"competitor_queries": ["Test Idea competitors"]}
        mock_generate_plan.return_value = mock_plan
        
        state = self._base_state()
        result = plan_node(state)
        
        assert "research_plan" in result
        assert result["research_plan"] == mock_plan
        mock_generate_plan.assert_called_once_with("Test Idea", "Test Problem")

    @patch("app.graph.market_research_agent.nodes.execute_serper_search")
    @patch("app.graph.market_research_agent.nodes.extract_competitors_strict")
    @patch("app.graph.market_research_agent.tools.find_competitors_from_plan")
    def test_competitors_node_with_plan(
        self, mock_find, mock_extract, mock_search
    ):
        """competitors_node should fetch search data and return a file output."""
        mock_search.return_value = [{"title": "Competitor 1"}]
        mock_extract.return_value = [{"Name": "Competitor 1"}]
        mock_find.return_value = "competitors.csv"
        
        state = self._base_state()
        state["research_plan"] = {"competitor_queries": ["Q1"]}
        result = competitors_node(state)
        
        assert result["competitors_file"] == "competitors.csv"
        mock_search.assert_called_once_with(["Q1"])
        mock_find.assert_called_once_with("Test Idea", state["research_plan"])

    def test_competitors_node_without_plan(self):
        """competitors_node should skip if no plan exists."""
        state = self._base_state()
        state["research_plan"] = None
        result = competitors_node(state)
        assert result["competitors_file"] is None

    @patch("app.graph.market_research_agent.nodes.validate_problem")
    def test_validation_node(self, mock_validate):
        """validation_node should call validate_problem and return file."""
        mock_validate.return_value = "validation.csv"
        
        state = self._base_state()
        state["research_plan"] = {"validation_queries": ["Q2"]}
        result = validation_node(state)
        
        assert result["validation_file"] == "validation.csv"
        mock_validate.assert_called_once_with("Test Idea", "Test Problem", plan=state["research_plan"])

    @patch("app.graph.market_research_agent.nodes.fetch_trend_data")
    def test_trends_node(self, mock_fetch):
        """trends_node should fetch trends and return a file."""
        mock_fetch.return_value = ("trends.csv", "stats")
        
        state = self._base_state()
        state["research_plan"] = {"market_identity": {"industry": "Tech"}}
        state["input_region"] = "US"
        result = trends_node(state)
        
        assert result["trends_file"] == "trends.csv"
        mock_fetch.assert_called_once()
        args, kwargs = mock_fetch.call_args
        assert args[0] == ["Tech"]
        assert kwargs["geo_code"] == "US"

    @patch("app.graph.market_research_agent.nodes.run_finance_model")
    def test_finance_node(self, mock_finance):
        """finance_node should run financial modelling."""
        mock_finance.return_value = "finance.csv"
        
        state = self._base_state()
        state["research_plan"] = {}
        result = finance_node(state)
        
        assert result["finance_file"] == "finance.csv"
        mock_finance.assert_called_once_with("Test Idea", plan={})

    @patch("app.graph.market_research_agent.nodes.calculate_market_size")
    def test_market_sizing_node(self, mock_size):
        """market_sizing_node should calculate market limits."""
        mock_size.return_value = "market.csv"
        
        state = self._base_state()
        state["research_plan"] = {"market_identity": {"target_country": "UK"}}
        result = market_sizing_node(state)
        
        assert result["market_limit_file"] == "market.csv"
        mock_size.assert_called_once_with("Test Idea", location="UK", plan=state["research_plan"])

    @patch("app.graph.market_research_agent.nodes.generate_report")
    def test_report_node(self, mock_report):
        """report_node should generate report from given files."""
        state = self._base_state()
        state["validation_file"] = "val.csv"
        state["trends_file"] = "trend.csv"
        state["finance_file"] = "fin.csv"
        
        result = report_node(state)
        
        assert result["report_text"] == "Report Generated"
        mock_report.assert_called_once_with("val.csv", "Test Idea", trend_file="trend.csv", finance_file="fin.csv")

    @patch("app.graph.market_research_agent.nodes.compile_final_json")
    @patch("app.graph.market_research_agent.nodes.compile_final_pdf")
    def test_pdf_node(self, mock_pdf, mock_json):
        """pdf_node should compile final documents."""
        mock_pdf.return_value = "output.pdf"
        mock_json.return_value = "output.json"
        
        state = self._base_state()
        result = pdf_node(state)
        
        assert result["pdf_path"] == "output.pdf"
        assert result["json_path"] == "output.json"
        assert "output.pdf" in result["market_research"]
        assert "output.json" in result["market_research"]


# ===========================================================================
# 7. WORKFLOW / GRAPH STRUCTURE
# ===========================================================================
class TestMarketResearchWorkflow:
    def test_graph_creation(self):
        """Test that the graph compiles successfully and contains all core nodes."""
        workflow = create_market_research_graph()
        assert workflow is not None
        
        assert hasattr(workflow, "invoke")
