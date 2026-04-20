"""
SWOT Generator Agent — Integrated Test Suite
===================================
This file contains unit tests for the SWOT pipeline in the Document Generator.

Sections:
  1. STATE & SCHEMA VALIDATION
  2. SWOT AGENT Nodes
"""

import pytest
from unittest.mock import patch

# --- Imports from application ---
from app.graph.document_generator.state import DocumentGeneratorState
from app.graph.document_generator.nodes import (
    scrape_competitors_node,
    analyze_gaps_node,
    scrape_barriers_node,
    analyze_weaknesses_node
)

# ===========================================================================
# 1. STATE & SCHEMA VALIDATION
# ===========================================================================
class TestSWOTState:
    def test_state_initialization(self):
        """Test that the state can be initialized with required fields."""
        state: DocumentGeneratorState = {
            "document_type": "swot",
            "idea_name": "AI Startup",
            "idea_description": "An AI platform",
            "region": "US",
            "market_research": {"some": "data"},
            "comment": None,
            "competitor_analysis_document": None,
            "swot_document": None,
            "errors": []
        }
        assert state["idea_name"] == "AI Startup"
        assert state["document_type"] == "swot"

# ===========================================================================
# 2. SWOT AGENT Nodes
# ===========================================================================
class TestSWOTNodes:
    def _base_state(self) -> DocumentGeneratorState:
        return {
            "document_type": "swot",
            "idea_name": "Test Idea",
            "idea_description": "Test Problem",
            "region": "Global",
            "market_research": {"some": "data"},
            "comment": None,
            "errors": []
        }

    @patch("app.graph.document_generator.nodes.scrape_competitor_reviews")
    def test_scrape_competitors_node(self, mock_scrape):
        """Test scrape_competitors_node calls scraper correctly."""
        mock_scrape.return_value = {"reviews": "mock_data"}
        state = self._base_state()
        result = scrape_competitors_node(state)
        
        assert "reviews_data" in result
        assert result["reviews_data"] == {"reviews": "mock_data"}
        mock_scrape.assert_called_once()

    @patch("app.graph.document_generator.nodes.analyze_competitive_gap")
    def test_analyze_gaps_node(self, mock_analyze):
        """Test analyze_gaps_node processes reviews correctly."""
        mock_analyze.return_value = {"gap": "mock_data"}
        state = self._base_state()
        state["reviews_data"] = {"reviews": "data"}
        result = analyze_gaps_node(state)
        
        assert "gap_data" in result
        assert result["gap_data"] == {"gap": "mock_data"}

    @patch("app.graph.document_generator.nodes.scrape_regulatory_barriers")
    def test_scrape_barriers_node(self, mock_analyze):
        """Test scrape_barriers_node correctly evaluates barriers."""
        mock_analyze.return_value = {"barriers": "mock_data"}
        state = self._base_state()
        result = scrape_barriers_node(state)
        
        assert "barriers_data" in result
        assert result["barriers_data"] == {"barriers": "mock_data"}

    @patch("app.graph.document_generator.nodes.analyze_weaknesses")
    def test_analyze_weaknesses_node(self, mock_analyze):
        """Test analyze_weaknesses_node evaluates state properly."""
        mock_analyze.return_value = {"weak": "data"}
        state = self._base_state()
        result = analyze_weaknesses_node(state)
        
        assert "weaknesses_data" in result
        assert result["weaknesses_data"] == {"weak": "data"}
