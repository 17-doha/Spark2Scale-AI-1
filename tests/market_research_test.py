import pytest
import json
from unittest.mock import patch, AsyncMock, MagicMock
import pandas as pd

# --- Imports from application ---
from app.graph.market_research_agent.helpers.pdf_utils import remove_emojis
from app.graph.market_research_agent.helpers.market_sizing_validator import RealisticMarketSizer
from app.graph.market_research_agent.helpers.finance_utils import detect_currency
from app.graph.market_research_agent.helpers.research_utils import extract_competitors_strict
from app.graph.market_research_agent.helpers.validator_utils import analyze_pain_intensity

# ==========================================
# 1. TESTS FOR pdf_utils.py (Data & Parsing)
# ==========================================

def test_remove_emojis():
    """Test removing emojis from text."""
    # Note: 'remove_emojis' keeps ascii and arabic, removes others.
    result = remove_emojis("Hello World 🌍")
    assert result.strip() == "Hello World"
    
    # Check if None or non-string is passed
    assert remove_emojis(None) is None
    assert remove_emojis(123) == 123

# ==========================================
# 2. TESTS FOR market_sizing_validator.py
# ==========================================

def test_extract_number_from_text():
    """Test extracting numbers with different scales (Millions, Billions, Trillions)."""
    # Valid formats
    assert RealisticMarketSizer.extract_number_from_text("$5.2 Billion") == 5200.0
    assert RealisticMarketSizer.extract_number_from_text("500 Million") == 500.0
    assert RealisticMarketSizer.extract_number_from_text("$1.5 Trillion") == 1500000.0
    assert RealisticMarketSizer.extract_number_from_text("10 Thousand") == 0.01

    # Invalid format handling
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
    # 'terrible', 'hate', 'nightmare' are high pain keywords, should return 1.3
    intensity = analyze_pain_intensity(evidence_list_high_pain)
    assert intensity == 1.3
    
    evidence_list_low_pain = [
        {"title": "It's nice to have", "snippet": "minor inconvenience sometimes"}
    ]
    # 'nice to have', 'minor', 'sometimes' are low pain keywords, should return 0.7
    intensity_low = analyze_pain_intensity(evidence_list_low_pain)
    assert intensity_low == 0.7
    
    # Empty list falls back to 1.0
    assert analyze_pain_intensity([]) == 1.0

# ==========================================
# 4. TESTS FOR LLM / APIs Integration (Mocks)
# ==========================================

@patch("app.graph.market_research_agent.helpers.finance_utils.call_gemini")
def test_detect_currency_mock(mock_call_gemini):
    """Test detecting location and currency using mocked gemini call."""
    # Arrange
    mock_response = MagicMock()
    # Mocking Gemini text response wrapped in markdown block
    mock_response.text = '```json\n{"country": "Egypt", "currency_code": "EGP", "currency_symbol": "EGP"}\n```'
    mock_call_gemini.return_value = mock_response

    # Act
    result = detect_currency("Delivery app in Egypt")

    # Assert
    assert result["country"] == "Egypt"
    assert result["currency_code"] == "EGP"

@patch("app.graph.market_research_agent.helpers.research_utils.call_gemini")
def test_extract_competitors_strict_mock(mock_call_gemini):
    """Test competitor extraction functionality with LLM mocked."""
    # Arrange
    mock_response = MagicMock()
    mock_response.text = '```json\n[{"Name": "Competitor A", "Features": "Feature 1"}]\n```'
    mock_call_gemini.return_value = mock_response

    search_data = [{"title": "Competitor A page", "snippet": "Best product"}]
    
    # Act
    result = extract_competitors_strict(search_data, "My App")

    # Assert
    assert len(result) == 1
    assert result[0]["Name"] == "Competitor A"
