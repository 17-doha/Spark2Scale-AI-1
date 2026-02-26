import pytest
import json
from unittest.mock import patch, AsyncMock, MagicMock

# --- Imports from your application ---
from app.graph.evaluation_agent.helpers import (
    extract_team_data,
    safe_score_numeric,
    parse_and_repair_json
)
from app.graph.evaluation_agent.tools import (
    tech_stack_detective,
    tam_sam_verifier_tool,
    team_scoring_agent,
    calculate_economics_with_judgment
)

# --- Additional Imports Needed ---
from app.graph.evaluation_agent.helpers import (
    extract_problem_data,
    extract_market_data,
    extract_traction_data,
    check_missing_fields,
    generate_queries,
    get_market_signals_serper
)
from app.graph.evaluation_agent.tools import (
    contradiction_check,
    verify_problem_claims,
    problem_scoring_agent,
    regulation_trend_radar_tool,
    market_scoring_agent,
    evaluate_business_model_with_context,
    get_funding_benchmarks
)

# ==========================================
# 1. TESTS FOR helpers.py (Data & Parsing)
# ==========================================

def test_extract_team_data():
    """Test extracting team data from a deeply nested evaluation JSON."""
    # Arrange
    dummy_data = {
        "startup_evaluation": {
            "founder_and_team": {
                "founders": [
                    {
                        "name": "Jane Doe",
                        "role": "CEO",
                        "ownership_percentage": 50,
                        "prior_experience": "Ex-Google",
                        "years_direct_experience": 10,
                        "founder_market_fit_statement": "Built ad-tech before"
                    }
                ],
                "execution": {
                    "full_time_start_date": "2023-01-01",
                    "key_shipments": [{"date": "2023-06-01", "item": "MVP"}]
                }
            },
            "problem_definition": {
                "problem_statement": "Testing is hard.",
                "current_solution": "Manual testing",
                "gap_analysis": "Automated AI testing"
            }
        }
    }

    # Act
    result = extract_team_data(dummy_data)

    # Assert
    assert len(result["founders"]) == 1
    assert result["founders"][0]["name"] == "Jane Doe"
    assert result["founders"][0]["equity"] == 50
    assert result["execution_history"]["start_date"] == "2023-01-01"
    assert result["problem_context"]["statement"] == "Testing is hard."

def test_safe_score_numeric():
    """Test converting raw 'X/5' string scores into 0-100 integer bounds."""
    # Valid formats
    assert safe_score_numeric({"score": "4/5"}) == 80
    assert safe_score_numeric({"score": "3.5/5"}) == 70
    assert safe_score_numeric({"score": "5"}) == 100
    
    # Invalid formats should degrade gracefully to 0
    assert safe_score_numeric({"score": "Invalid"}) == 0
    assert safe_score_numeric({}) == 0

def test_parse_and_repair_json():
    """Test the robust JSON parser's ability to handle LLM markdown hallucinations."""
    # Valid JSON
    assert parse_and_repair_json('{"key": "value"}') == {"key": "value"}
    
    # JSON wrapped in markdown code blocks
    markdown_json = "```json\n{\"key\": \"value\"}\n```"
    assert parse_and_repair_json(markdown_json) == {"key": "value"}
    
    # Completely broken JSON should return a safe fallback dictionary
    broken_str = "This is not JSON at all, I am an AI and I like to chat."
    result = parse_and_repair_json(broken_str)
    assert "score_numeric" in result
    assert result["score_numeric"] == 0
    assert "Error parsing" in result.get("explanation", "")


# ==========================================
# 2. TESTS FOR tools.py (Agents & APIs)
# ==========================================

@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.builtwith.parse")
async def test_tech_stack_detective(mock_builtwith_parse):
    """Test the tech stack detective without actually hitting the network."""
    # Arrange: Mock the synchronous builtwith response
    mock_builtwith_parse.return_value = {"javascript-frameworks": ["React", "Vue"]}
    
    # Act
    result = await tech_stack_detective("https://example.com")
    
    # Assert
    assert result["status"] == "Success"
    assert "React" in result["technologies_found"]
    assert "Vue" in result["technologies_found"]

@pytest.mark.asyncio
async def test_tech_stack_detective_no_url():
    """Test early exit for missing URLs."""
    result = await tech_stack_detective("")
    assert result["verdict"] == "No URL"

@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.os.environ.get")
@patch("app.graph.evaluation_agent.tools.aiohttp.ClientSession.post")
async def test_tam_sam_verifier_tool(mock_post, mock_env):
    """Test the TAM Search tool by mocking the Serper API network call."""
    # Arrange
    mock_env.return_value = "fake_api_key"
    
    # Create a mock response for aiohttp's async context manager
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "organic": [
            {"title": "TAM Study", "snippet": "The market is $10B."}
        ]
    }
    mock_post.return_value.__aenter__.return_value = mock_response
    
    # Act
    result = await tam_sam_verifier_tool("AI Startups", "Global", "$5B")
    
    # Assert
    assert result["tool"] == "TAM_Verifier"
    assert result["status"] == "Success"
    assert "The market is $10B." in result["search_evidence"]

@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.get_llm")
async def test_team_scoring_agent(mock_get_llm):
    """Test the LangChain scoring agent by patching the chain's ainvoke method."""
    # Arrange
    mock_llm_instance = AsyncMock()
    mock_get_llm.return_value = mock_llm_instance
    
    # Instead of deep-mocking the entire LCEL chain, we patch the final parser's invoke
    with patch("app.graph.evaluation_agent.tools.StrOutputParser.ainvoke", new_callable=AsyncMock) as mock_chain_ainvoke:
        # Mock the exact string the LLM would theoretically return
        mock_chain_ainvoke.return_value = '{"score": "4/5", "explanation": "Great team"}'
        
        data_package = {
            "user_data": {"founders": []},
            "risk_report": "None",
            "contradiction_report": "None",
            "missing_report": "None"
        }
        
        # Act
        result = await team_scoring_agent(data_package)
        
        # Assert
        assert result["score"] == "4/5"
        assert result["explanation"] == "Great team"
        assert result["score_numeric"] == 80  # 4/5 * 20

@patch("app.graph.evaluation_agent.tools.get_llm")
def test_calculate_economics_with_judgment(mock_get_llm):
    """Test the synchronous logic mixed with AI judgment for Unit Economics."""
    # Arrange
    gtm_data = {
        "unit_economics": {
            "burn_rate": "10000",
            "total_users": "500",
            "paid_users": "50",
            "revenue": "2000",
            "price_point": "40"
        },
        "context": {"founded_date": "2023-01-01", "stage": "Seed"},
        "strategy": {"icp_description": "B2B SaaS"}
    }
    
    # Arrange: Mock the synchronous LangChain invocation
    with patch("app.graph.evaluation_agent.tools.StrOutputParser.invoke") as mock_chain_invoke:
        mock_chain_invoke.return_value = '{"verdict": "Healthy metrics", "score": "4/5"}'
        
        # Act
        result = calculate_economics_with_judgment(gtm_data)
        
        # Assert the purely deterministic math
        assert result["monthly_burn"] == "$10000"
        assert result["price_point"] == "$40"
        assert result["conversion_rate"] == 10.0  # 50 / 500 * 100
        
        # Assert that the AI analysis got stitched back in correctly
        assert result["ai_analysis"]["verdict"] == "Healthy metrics"

@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.get_llm")
async def test_contradiction_check(mock_get_llm):
    """Test standard StrOutputParser risk agents."""
    with patch("app.graph.evaluation_agent.tools.StrOutputParser.ainvoke", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = "No contradictions found."
        
        result = await contradiction_check({"data": "test"}, "Find contradictions in {json_data}")
        
        # We only need to assert that the function executes and returns our mocked output
        assert result == "No contradictions found."
        mock_invoke.assert_called_once()

        
@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.get_llm")
@patch("app.graph.evaluation_agent.tools.os.environ.get")
@patch("app.graph.evaluation_agent.tools.aiohttp.ClientSession.post")
async def test_verify_problem_claims(mock_post, mock_env, mock_get_llm):
    """Test complex tool involving LLM query generation + Parallel Async Searching."""
    mock_env.return_value = "fake_api_key"
    
    # Mock LLM generating the JSON queries
    mock_llm_instance = AsyncMock()
    mock_llm_instance.ainvoke.return_value.content = '{"pain_query": "Q1", "symptom_query": "Q2", "solution_query": "Q3"}'
    mock_get_llm.return_value = mock_llm_instance
    
    # Mock Aiohttp Search Responses
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"organic": [{"title": "Hit", "link": "url", "snippet": "Text"}]}
    mock_post.return_value.__aenter__.return_value = mock_response

    result = await verify_problem_claims("Bad APIs", "Devs")
    
    # Assert
    assert result["generated_queries"]["pain_query"] == "Q1"
    assert len(result["pain_validation_search"]) == 2 # Q1 + Q2 hits
    assert len(result["competitor_search"]) == 1 # Q3 hit
    assert result["pain_validation_search"][0]["title"] == "Hit"

@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.get_llm")
async def test_problem_scoring_agent(mock_get_llm):
    """Test scoring agent repairing JSON and converting string score to numeric."""
    with patch("app.graph.evaluation_agent.tools.StrOutputParser.ainvoke", new_callable=AsyncMock) as mock_invoke:
        # Mocking an LLM returning Markdown JSON
        mock_invoke.return_value = "```json\n{\"score\": \"3.5/5\", \"explanation\": \"Good\"}\n```"
        
        result = await problem_scoring_agent({
            "problem_definition": {}, "search_report": {},
            "missing_report": "", "risk_report": "", "contradiction_report": ""
        })
        
        assert result["score"] == "3.5/5"
        assert result["explanation"] == "Good"
        assert result["score_numeric"] == 70 # 3.5 * 20

@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.os.environ.get")
@patch("app.graph.evaluation_agent.tools.aiohttp.ClientSession.post")
async def test_regulation_trend_radar_tool(mock_post, mock_env):
    """Test dual-query radar search for regulations and trends."""
    mock_env.return_value = "fake_api_key"
    
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"organic": [{"snippet": "Reg hit 1"}]}
    mock_post.return_value.__aenter__.return_value = mock_response
    
    result = await regulation_trend_radar_tool("Fintech", "USA")
    
    assert result["tool"] == "Regulation_Radar"
    assert "Reg hit 1" in result["findings"]["regulatory_evidence"]
    assert "Reg hit 1" in result["findings"]["trend_evidence"]

@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.get_llm")
async def test_evaluate_business_model_with_context(mock_get_llm):
    """Test AI business math integration."""
    with patch("app.graph.evaluation_agent.tools.StrOutputParser.ainvoke", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = '{"verdict": "Solid Margin"}'
        
        data = {
            "monetization_structure": {"price_point": "100", "gross_margin": "80"},
            "cash_health": {"burn_rate": "50000", "runway_months": "12"},
            "context": {"company_name": "TestCo"}
        }
        
        result = await evaluate_business_model_with_context(data)
        
        assert result["metrics"]["monthly_burn"] == "$50000"
        assert result["metrics"]["runway_months"] == 12.0
        assert result["metrics"]["gross_margin"] == "80.0%"
        assert result["ai_analysis"]["verdict"] == "Solid Margin"

@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.os.environ.get")
@patch("app.graph.evaluation_agent.tools.aiohttp.ClientSession.post")
async def test_get_funding_benchmarks(mock_post, mock_env):
    """Test fallback logic for empty benchmarks."""
    mock_env.return_value = "fake_api_key"
    
    # Simulate a failed search or no organic hits
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"organic": []}
    mock_post.return_value.__aenter__.return_value = mock_response
    
    result = await get_funding_benchmarks("UK", "Seed", "MedTech")
    
    assert result == "No specific benchmarks found."

@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.get_llm")
async def test_market_scoring_agent_rubric_logic(mock_get_llm):
    """Test that market scoring correctly maps numeric scores to rubrics."""
    with patch("app.graph.evaluation_agent.tools.StrOutputParser.ainvoke", new_callable=AsyncMock) as mock_invoke:
        # Score of 5/5 maps to 100, which maps to Blue Ocean (100 // 20 = 5)
        mock_invoke.return_value = '{"score": "5/5"}'
        
        result = await market_scoring_agent({"internal_data": {}})
        
        assert result["score_numeric"] == 100
        assert result["rubric_rating"] == "Blue Ocean"





def test_extract_problem_data():
    """Test the problem data extraction logic."""
    data = {
        "startup_evaluation": {
            "problem_definition": {
                "problem_statement": "Manual testing is slow.",
                "frequency": "High",
                "impact_metrics": {"cost_type": "Time", "description": "Losing 10h/week"}
            },
            "market_and_scope": {
                "beachhead_market": "QA Engineers"
            },
            "founder_and_team": {
                "founders": [{"founder_market_fit_statement": "I was a QA engineer."}]
            }
        }
    }
    res = extract_problem_data(data)
    
    assert res["problem_core"]["frequency"] == "High"
    assert res["audience"]["beachhead"] == "QA Engineers"
    assert "I was a QA engineer." in res["founder_alignment_statements"]

def test_extract_traction_data_pre_seed():
    """Test traction extraction logic branching (Pre-Seed)."""
    data = {
        "company_snapshot": {"current_stage": "Pre-Seed"},
        "traction_metrics": {"user_count": 150, "early_revenue": "0"},
        "product_and_solution": {"defensibility_moat": "Proprietary AI"}
    }
    res = extract_traction_data(data)
    
    assert res["analysis_type"] == "Pre-Seed Validation"
    assert res["validation_signals"]["users_total"] == 150
    assert res["defensibility"] == "Proprietary AI"

def test_check_missing_fields():
    """Test recursive missing field detection."""
    data = {
        "valid_field": "Hello",
        "empty_string": "",
        "empty_list": [],
        "nested": {
            "good": 100,
            "bad_null": None
        }
    }
    errors = check_missing_fields(data)
    
    # Should find 3 errors: empty_string, empty_list, bad_null
    assert len(errors) == 3
    assert any("empty_string" in e for e in errors)
    assert any("empty_list" in e for e in errors)
    assert any("nested.bad_null" in e for e in errors)

def test_generate_queries():
    """Test query generator for search tools."""
    vision_data = {"category_play": {"definition": "SpaceTech"}}
    topic, queries = generate_queries(vision_data)
    
    assert topic == "SpaceTech"
    assert len(queries) == 4
    assert any("SpaceTech" in q for q in queries)

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