"""
Competitor Analysis (CA) Agent — Integrated Test Suite
===================================
This file contains unit tests for the Competitor Analysis pipeline.

Sections:
  1. STATE & SCHEMA VALIDATION
  2. COMPETITOR ANALYSIS AGENT Nodes
"""

import pytest
from unittest.mock import patch, MagicMock

# --- Imports from application ---
from app.graph.document_generator.state import DocumentGeneratorState
from app.graph.document_generator.competitor_analysis_matrix.ca_nodes import (
    extract_competitors_from_market_research,
    enrich_competitor_links,
    enrich_market_intelligence,
    enrich_product_reality,
    classify_competitor_type,
    build_competitor_matrix
)

# ===========================================================================
# 1. STATE & SCHEMA VALIDATION
# ===========================================================================
class TestCAState:
    def test_state_initialization(self):
        """Test that the state can be initialized with required fields."""
        state: DocumentGeneratorState = {
            "document_type": "competitor_analysis",
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
        assert state["document_type"] == "competitor_analysis"

# ===========================================================================
# 2. COMPETITOR ANALYSIS AGENT Nodes
# ===========================================================================
class TestCompetitorAnalysisNodes:
    def _base_state(self) -> DocumentGeneratorState:
        return {
            "document_type": "competitor_analysis",
            "idea_name": "Test App",
            "idea_description": "A robust application",
            "region": "Global",
            "market_research": {
                "competitors": [{"Name": "CompA"}, {"Name": "CompB"}]
            },
            "errors": []
        }

    def test_extract_competitors_from_market_research(self):
        """Test extraction of competitor profiles from market research JSON."""
        state = self._base_state()
        result = extract_competitors_from_market_research(state)
        assert "competitors" in result
        assert len(result["competitors"]) == 2
        assert result["competitors"][0]["name"] == "CompA"
        assert result["competitors"][1]["name"] == "CompB"

    @patch("app.graph.document_generator.competitor_analysis_matrix.ca_nodes.execute_serper_search")
    def test_enrich_competitor_links(self, mock_search):
        """Test enrichment of links safely avoids cross-contamination."""
        # Simple mock for _search_one wrapper
        mock_search.return_value = [{"link": "https://compa.com", "snippet": "Company A"}]
        
        state = self._base_state()
        state["competitors"] = [{
            "name": "CompA", 
            "company_website": None,
            "sw_profile": None,
            "linkedin_url": None, 
            "physical_location": None
        }]
        result = enrich_competitor_links(state)
        
        assert len(result["competitors"]) == 1
        assert result["competitors"][0]["company_website"] == "https://compa.com"
        assert mock_search.call_count >= 4 # 4-6 intent calls based on review site matches

    @patch("app.graph.document_generator.competitor_analysis_matrix.ca_nodes.call_gemini")
    @patch("app.graph.document_generator.competitor_analysis_matrix.ca_nodes.execute_serper_search")
    def test_enrich_market_intelligence(self, mock_search, mock_gemini):
        """Test market intelligence correctly parses Gemini's json response."""
        mock_search.return_value = [{"link": "https://compa.com", "snippet": "Pricing is 10$"}]
        
        mock_response = MagicMock()
        mock_response.text = '```json\n{"CompA": {"pricing_model": "Freemium"}}\n```'
        mock_gemini.return_value = mock_response
        
        state = self._base_state()
        state["competitors"] = [{
            "name": "CompA", 
            "company_website": "https://compa.com",
            "sw_profile": None,
            "target_audience": None,
            "value_proposition": None,
            "pricing_model": None
        }]
        
        result = enrich_market_intelligence(state)
        assert result["competitors"][0]["pricing_model"] == "Freemium"

    @patch("app.graph.document_generator.competitor_analysis_matrix.ca_nodes.call_gemini")
    def test_classify_competitor_type(self, mock_gemini):
        """Test classification correctly assigns direct/indirect types."""
        mock_response = MagicMock()
        mock_response.text = '```json\n{"CompA": "direct", "CompB": "indirect"}\n```'
        mock_gemini.return_value = mock_response
        
        state = self._base_state()
        state["competitors"] = [{
            "name": "CompA", 
            "company_website": "https://compa.com",
            "competitor_type": None
        }]
        
        result = classify_competitor_type(state)
        assert result["competitors"][0]["competitor_type"] == "direct"
