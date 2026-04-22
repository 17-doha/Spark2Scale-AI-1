import pytest
import json
from unittest.mock import patch, MagicMock

# --- Imports from application ---
from app.graph.recommendation_agent.helpers import calculate_trigger_strength, extract_key_insights
from app.graph.recommendation_agent.patterns import detect_patterns
from app.graph.recommendation_agent.tools import analyze_wb_indicator, run_market_intel
from app.graph.recommendation_agent.node import AgentNodes
from app.graph.recommendation_agent.schema import StartupData, StartupScores, SectionScore


# ==========================================
# SHARED TEST FIXTURES
# ==========================================

def make_scores(overrides=None):
    """
    Build a mock dict-of-dicts exactly as detect_patterns() lambdas expect.
    Lambda triggers use s['team']['score'] and s['gtm']['description'], etc.
    """
    defaults = {
        "team":       {"score": 2.0, "description": "solo founder struggling and not selling"},
        "problem":    {"score": 3.0, "description": "vague customer language conceptual problem"},
        "product":    {"score": 4.0, "description": "engineering-led with assumptions untested"},
        "market":     {"score": 3.0, "description": "fragmented smes unclear icp"},
        "traction":   {"score": 2.0, "description": "spiky metrics with churn low retention"},
        "gtm":        {"score": 2.0, "description": "reverting to ads strong demos"},
        "economics":  {"score": 3.0, "description": "pricing friction"},
        "ops":        {"score": 2.0, "description": "no weekly planning"},
        "vision":     {"score": 2.0, "description": "rapid narrative changes"},
    }
    if overrides:
        defaults.update(overrides)
    return defaults  # plain dict — subscript access works directly


def make_startup_data(**score_overrides) -> StartupData:
    """Build a real StartupData Pydantic object for node tests."""
    raw = make_scores(score_overrides or {})
    scores = StartupScores(
        team=SectionScore(**raw["team"]),
        problem=SectionScore(**raw["problem"]),
        product=SectionScore(**raw["product"]),
        market=SectionScore(**raw["market"]),
        traction=SectionScore(**raw["traction"]),
        gtm=SectionScore(**raw["gtm"]),
        economics=SectionScore(**raw["economics"]),
        ops=SectionScore(**raw["ops"]),
        vision=SectionScore(**raw["vision"]),
    )
    return StartupData(stage="Seed", company_context="A fintech in Egypt", scores=scores)



# ==========================================
# 1. TESTS FOR helpers.py
# ==========================================

def test_calculate_trigger_strength_high():
    """Base weight 0.7 × multiplier 1.5 should equal 1.05."""
    multipliers = {"high": 1.5, "medium": 1.3, "low": 1.1}
    result = calculate_trigger_strength("high", multipliers, cross_category_support=False)
    assert result == 1.05


def test_calculate_trigger_strength_with_cross_category():
    """Cross-category support adds a 1.2× boost: 0.7 × 1.5 × 1.2 = 1.26."""
    multipliers = {"high": 1.5, "medium": 1.3, "low": 1.1}
    result = calculate_trigger_strength("high", multipliers, cross_category_support=True)
    assert result == 1.26


def test_calculate_trigger_strength_unknown_severity():
    """Unknown severity falls back to multiplier 1.0: 0.7 × 1.0 = 0.7."""
    multipliers = {"high": 1.5}
    result = calculate_trigger_strength("unknown_sev", multipliers, cross_category_support=False)
    assert result == 0.7


def test_extract_key_insights_full():
    """Correctly parses a complete startup evaluation dict into flat insights."""
    raw = {
        "startup_evaluation": {
            "company_snapshot": {
                "company_name": "FinBoost",
                "location": "Egypt",
                "industry": "Fintech",
                "current_stage": "Seed",
                "current_round": {"target_amount": "$500k"}
            },
            "problem_definition": {
                "problem_statement": "SMEs cannot access credit.",
                "gap_analysis": "Banks ignore digital-native businesses.",
                "evidence": {"customer_quotes": ["'We can't get loans' - Ahmed"]}
            },
            "founder_and_team": {
                "founders": [{"prior_experience": "Ex-CIB", "founder_market_fit_statement": "Deep credit expertise"}]
            },
            "product_and_solution": {
                "differentiation": "Real-time API scoring",
                "core_stickiness": "Automated VAT filing"
            },
            "traction_metrics": {
                "active_users_monthly": 120,
                "early_revenue": "EGP 60,000"
            },
            "vision_and_strategy": {"five_year_vision": "Become MENA trade-finance backbone."},
            "market_and_scope": {"beachhead_market": "Cairo grocery retailers"}
        }
    }
    insights = extract_key_insights(raw)

    assert insights["company_name"] == "FinBoost"
    assert insights["country"] == "Egypt"
    assert insights["sector"] == "Fintech"
    assert insights["stage"] == "Seed"
    assert insights["target_raise"] == "$500k"
    assert insights["problem_statement"] == "SMEs cannot access credit."
    assert insights["customer_quotes"] == ["'We can't get loans' - Ahmed"]
    assert insights["active_users"] == 120
    assert insights["beachhead_market"] == "Cairo grocery retailers"


def test_extract_key_insights_country_fallback():
    """If 'location' is missing, the function should sniff text for a country name."""
    raw = {
        "startup_evaluation": {
            "company_snapshot": {"company_name": "X", "info": "Based in Saudi Arabia"},
            "problem_definition": {},
            "founder_and_team": {"founders": [{}]},
            "product_and_solution": {},
            "traction_metrics": {}
        }
    }
    insights = extract_key_insights(raw)
    assert insights["country"] == "saudi arabia"


def test_extract_key_insights_sector_inferred_from_text():
    """If 'industry' key is absent, sector should be inferred from problem text."""
    raw = {
        "startup_evaluation": {
            "company_snapshot": {"company_name": "HealthApp", "location": "Jordan"},
            "problem_definition": {"problem_statement": "We fix medical supply issues."},
            "founder_and_team": {"founders": [{}]},
            "product_and_solution": {"differentiation": "health tracking"},
            "traction_metrics": {}
        }
    }
    insights = extract_key_insights(raw)
    assert insights["sector"] == "healthtech"


# ==========================================
# 2. TESTS FOR patterns.py
# ==========================================

def test_detect_patterns_returns_list():
    """detect_patterns should always return a list."""
    scores = make_scores()
    result = detect_patterns(scores)
    assert isinstance(result, list)


def test_detect_patterns_required_keys():
    """Every matched pattern must have the expected schema keys."""
    scores = make_scores()
    patterns = detect_patterns(scores)
    required_keys = {"pattern_id", "name", "severity", "strength_score", "strength_label", "template", "confidence", "confidence_reasoning"}
    for p in patterns:
        assert required_keys.issubset(p.keys()), f"Pattern {p.get('pattern_id')} missing required key"


def test_detect_patterns_team_pattern_fires():
    """FP-TEAM-001 should fire when GTM score ≤ 2 and description mentions 'not selling'."""
    scores = make_scores()
    pattern_ids = [p["pattern_id"] for p in detect_patterns(scores)]
    assert "FP-TEAM-001" in pattern_ids


def test_detect_patterns_solo_founder():
    """FP-TEAM-003 (Solo Founder Overload) fires on 'solo founder' text + ops score ≤ 3."""
    scores = make_scores({
        "team": {"score": 2.0, "description": "solo founder with no partners"},
        "ops":  {"score": 2.0, "description": "no planning structure"}
    })
    pattern_ids = [p["pattern_id"] for p in detect_patterns(scores)]
    assert "FP-TEAM-003" in pattern_ids


def test_detect_patterns_confidence_level_is_valid():
    """Confidence should always be one of 'HIGH', 'MEDIUM', or 'LOW'."""
    scores = make_scores()
    for p in detect_patterns(scores):
        assert p["confidence"] in {"HIGH", "MEDIUM", "LOW"}


def test_detect_patterns_sorted_by_strength():
    """Results must be sorted by strength_score descending."""
    scores = make_scores()
    patterns = detect_patterns(scores)
    strengths = [p["strength_score"] for p in patterns]
    assert strengths == sorted(strengths, reverse=True)


# ==========================================
# 3. TESTS FOR tools.py (Pure Logic)
# ==========================================

def test_analyze_wb_indicator_inflation():
    """Test the World Bank inflation threshold logic."""
    assert analyze_wb_indicator("inflation_rate", 25.0) == "high"
    assert analyze_wb_indicator("inflation_rate", 10.0) == "medium"
    assert analyze_wb_indicator("inflation_rate", 3.0) == "low"


def test_analyze_wb_indicator_gdp_growth():
    """Negative GDP growth should be flagged as 'high' risk."""
    assert analyze_wb_indicator("gdp_growth_rate", -1.0) == "high"
    assert analyze_wb_indicator("gdp_growth_rate", 1.5) == "medium"
    assert analyze_wb_indicator("gdp_growth_rate", 4.0) == "low"


def test_analyze_wb_indicator_none_value():
    """None value should return 'unknown' without crashing."""
    assert analyze_wb_indicator("inflation_rate", None) == "unknown"


def test_analyze_wb_indicator_unknown_indicator():
    """Unrecognized indicator names fall back to 'unknown'."""
    assert analyze_wb_indicator("nonexistent_indicator", 100.0) == "unknown"


@patch("app.graph.recommendation_agent.tools.fetch_world_bank_data")
@patch("app.graph.recommendation_agent.tools.fetch_tavily_news")
def test_run_market_intel_both_sources_present(mock_tavily, mock_wb):
    """With both WB + Tavily data, sources_used has both and confidence is 'medium'.
    NOTE: The current threshold in tools.py requires sources_count == 3 for 'high',
    but there are only 2 possible sources, so 'high' is unreachable. Max is 'medium'.
    """
    mock_wb.return_value = {
        "inflation_rate": {"value": 28.0, "risk": "high"},
        "gdp_growth_rate": {"value": 3.0, "risk": "low"}
    }
    mock_tavily.return_value = [
        {"title": "Egypt fintech ban news", "snippet": "There may be a ban on certain lending practices.", "url": "http://example.com", "source_domain": "example.com", "score": 0.9}
    ]

    insights = {"country": "Egypt", "sector": "fintech", "stage": "Seed"}
    result = run_market_intel(insights, tavily_api_key="fake-key")

    # Both sources active → sources_count == 2 → confidence == "medium"
    assert result["confidence"] == "medium"
    assert "World Bank" in result["sources_used"]
    assert "Tavily Search" in result["sources_used"]
    assert isinstance(result["risk_flags"], list)
    # 'ban' keyword in the news snippet should be flagged
    assert any("BAN" in flag for flag in result["risk_flags"])


@patch("app.graph.recommendation_agent.tools.fetch_world_bank_data")
@patch("app.graph.recommendation_agent.tools.fetch_tavily_news")
def test_run_market_intel_one_source_is_low(mock_tavily, mock_wb):
    """With only one source active, confidence should be 'low' (sources_count == 1)."""
    mock_wb.return_value = {"inflation_rate": {"value": 5.0, "risk": "low"}}
    mock_tavily.return_value = []  # no Tavily data

    insights = {"country": "Egypt", "sector": "fintech", "stage": "Seed"}
    result = run_market_intel(insights, tavily_api_key=None)

    assert result["confidence"] == "low"
    assert "World Bank" in result["sources_used"]
    assert "Tavily Search" not in result["sources_used"]


@patch("app.graph.recommendation_agent.tools.fetch_world_bank_data")
@patch("app.graph.recommendation_agent.tools.fetch_tavily_news")
def test_run_market_intel_low_confidence(mock_tavily, mock_wb):
    """With no data from either source, confidence should be 'low'."""
    mock_wb.return_value = {}
    mock_tavily.return_value = []

    insights = {"country": "", "sector": "", "stage": "Seed"}
    result = run_market_intel(insights, tavily_api_key=None)

    assert result["confidence"] == "low"
    assert result["sources_used"] == []


@patch("app.graph.recommendation_agent.tools.fetch_world_bank_data")
@patch("app.graph.recommendation_agent.tools.fetch_tavily_news")
def test_run_market_intel_funding_climate_active(mock_tavily, mock_wb):
    """News mentioning 'raised' or 'funding round' makes climate 'Active'."""
    mock_wb.return_value = {}
    mock_tavily.return_value = [
        {"title": "Local startup raised $5M", "snippet": "The company raised a funding round last month.", "url": "http://a.com", "source_domain": "a.com", "score": 0.8}
    ]

    insights = {"country": "Egypt", "sector": "fintech", "stage": "Seed"}
    result = run_market_intel(insights, tavily_api_key="fake-key")

    assert result["funding_climate"] == "Active"


# ==========================================
# 4. TESTS FOR node.py (LLM Mocked)
# ==========================================

@patch("app.graph.recommendation_agent.node.genai.Client")
def test_improve_statements_returns_parsed_json(mock_client_class):
    """improve_statements should return a parsed dict from the LLM JSON response."""
    mock_client = mock_client_class.return_value
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "problem_statement": {
            "original": "SMEs lack credit",
            "recommended": "90% of Cairo retail SMEs are rejected by banks due to collateral requirements.",
            "why_better": "Uses data instead of vague language."
        }
    })
    mock_client.models.generate_content.return_value = mock_response

    agent = AgentNodes(api_key="fake-key")
    result = agent.improve_statements({"problem_statement": "SMEs lack credit", "customer_quotes": []})

    assert isinstance(result, dict)
    assert "problem_statement" in result
    assert result["problem_statement"]["original"] == "SMEs lack credit"


@patch("app.graph.recommendation_agent.node.genai.Client")
def test_improve_statements_handles_markdown_wrapper(mock_client_class):
    """The LLM sometimes wraps JSON in markdown fences — the response parser should strip them."""
    mock_client = mock_client_class.return_value
    mock_response = MagicMock()
    mock_response.text = '```json\n{"problem_statement": {"original": "x", "recommended": "y", "why_better": "z"}}\n```'
    mock_client.models.generate_content.return_value = mock_response

    agent = AgentNodes(api_key="fake-key")
    result = agent.improve_statements({"problem_statement": "x", "customer_quotes": []})

    assert result["problem_statement"]["recommended"] == "y"
    

@patch("app.graph.recommendation_agent.node.genai.Client")
def test_synthesize_report_returns_text(mock_client_class):
    """synthesize_report should return the raw markdown string from the LLM."""
    mock_client = mock_client_class.return_value
    mock_response = MagicMock()
    mock_response.text = "# Spark2Scale Report\n\nYour startup needs to focus on sales."
    mock_client.models.generate_content.return_value = mock_response

    agent = AgentNodes(api_key="fake-key")
    data = make_startup_data()

    patterns = [
        {"pattern_id": "FP-TEAM-001", "name": "Founder Avoids the Hard Job", "template": "Do sales."}
    ]
    insights = {
        "company_name": "TestCo", "problem_statement": "Problem X",
        "customer_quotes": [], "target_raise": "$500k"
    }

    report = agent.synthesize_report(
        data, patterns, insights,
        replacements={},
        market_signals={"confidence": "high", "risk_flags": [], "country_risk": {}, "news_signals": []}
    )

    assert "Spark2Scale" in report
