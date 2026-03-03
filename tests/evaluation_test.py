import pytest
import json
from unittest.mock import patch, AsyncMock, MagicMock

# --- Imports from your application ---
from app.graph.evaluation_agent.helpers import (
    extract_team_data,
    safe_score_numeric,
    parse_and_repair_json,
    extract_problem_data,
    extract_market_data,
    extract_traction_data,
    check_missing_fields,
    generate_queries,
    get_market_signals_serper
)
from app.graph.evaluation_agent.tools.business_tools import (
    business_risk_agent,
    business_scoring_agent,
    evaluate_business_model_with_context,
    calculate_economics_with_judgment
)
from app.graph.evaluation_agent.tools.gtm_tools import (
    gtm_risk_agent, 
    gtm_scoring_agent
)
from app.graph.evaluation_agent.tools.market_tools import (
    market_scoring_agent, 
    tam_sam_verifier_tool, 
    regulation_trend_radar_tool
)
from app.graph.evaluation_agent.tools.operations_tools import (
    operations_risk_agent, 
    operations_scoring_agent
)
from app.graph.evaluation_agent.tools.problem_tools import (
    problem_scoring_agent, 
    verify_problem_claims, 
    loaded_risk_check_with_search
)
from app.graph.evaluation_agent.tools.product_tools import (
    product_scoring_agent, 
    tech_stack_detective, 
    local_dependency_detective
)
from  app.graph.evaluation_agent.tools.team_tools import (
    team_risk_check, 
    team_scoring_agent
)
from app.graph.evaluation_agent.tools.general_tools import contradiction_check  
from app.graph.evaluation_agent.tools.traction_tools import (
    traction_risk_agent, 
    traction_scoring_agent
)
from app.graph.evaluation_agent.tools.vision_tools import (
    vision_risk_agent, 
    vision_scoring_agent, 
    analyze_category_future, 
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
@patch("app.graph.evaluation_agent.tools.product_tools.builtwith.parse")
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
@patch("app.graph.evaluation_agent.tools.market_tools.os.environ.get")
@patch("app.graph.evaluation_agent.tools.market_tools.aiohttp.ClientSession.post")
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
@patch("app.graph.evaluation_agent.tools.team_tools.get_llm")
async def test_team_scoring_agent(mock_get_llm):
    """Test the LangChain scoring agent by patching the chain's ainvoke method."""
    # Arrange
    mock_llm_instance = MagicMock()  # <--- CHANGE THIS from AsyncMock to MagicMock
    mock_get_llm.return_value = mock_llm_instance
    
    # Instead of deep-mocking the entire LCEL chain, we patch the final parser's invoke
    with patch("app.graph.evaluation_agent.tools.team_tools.StrOutputParser.ainvoke", new_callable=AsyncMock) as mock_chain_ainvoke:
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

@patch("app.graph.evaluation_agent.tools.business_tools.get_llm")
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
    with patch("app.graph.evaluation_agent.tools.business_tools.StrOutputParser.invoke") as mock_chain_invoke:
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
@patch("app.graph.evaluation_agent.tools.general_tools.get_llm")
async def test_contradiction_check(mock_get_llm):
    """Test standard StrOutputParser risk agents."""
    with patch("app.graph.evaluation_agent.tools.general_tools.StrOutputParser.ainvoke", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = "No contradictions found."
        
        result = await contradiction_check({"data": "test"}, "Find contradictions in {json_data}")
        
        # We only need to assert that the function executes and returns our mocked output
        assert result == "No contradictions found."
        mock_invoke.assert_called_once()

        
@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.problem_tools.get_llm")
@patch("app.graph.evaluation_agent.tools.problem_tools.os.environ.get")
@patch("app.graph.evaluation_agent.tools.problem_tools.aiohttp.ClientSession.post")
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
@patch("app.graph.evaluation_agent.tools.problem_tools.get_llm")
async def test_problem_scoring_agent(mock_get_llm):
    """Test scoring agent repairing JSON and converting string score to numeric."""
    with patch("app.graph.evaluation_agent.tools.problem_tools.StrOutputParser.ainvoke", new_callable=AsyncMock) as mock_invoke:
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
@patch("app.graph.evaluation_agent.tools.market_tools.os.environ.get")
@patch("app.graph.evaluation_agent.tools.market_tools.aiohttp.ClientSession.post")
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
@patch("app.graph.evaluation_agent.tools.business_tools.get_llm")
async def test_evaluate_business_model_with_context(mock_get_llm):
    """Test AI business math integration."""
    with patch("app.graph.evaluation_agent.tools.business_tools.StrOutputParser.ainvoke", new_callable=AsyncMock) as mock_invoke:
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
@patch("app.graph.evaluation_agent.tools.vision_tools.os.environ.get")
@patch("app.graph.evaluation_agent.tools.vision_tools.aiohttp.ClientSession.post")
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
@patch("app.graph.evaluation_agent.tools.market_tools.get_llm")
async def test_market_scoring_agent_rubric_logic(mock_get_llm):
    """Test that market scoring correctly maps numeric scores to rubrics."""
    with patch("app.graph.evaluation_agent.tools.market_tools.StrOutputParser.ainvoke", new_callable=AsyncMock) as mock_invoke:
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


# ==========================================
# 3. NEW SCORING AGENT TESTS
# ==========================================

# --- VISION ---

@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.vision_tools.get_llm")
async def test_vision_scoring_agent(mock_get_llm):
    """vision_scoring_agent parses score and converts to numeric."""
    with patch(
        "app.graph.evaluation_agent.tools.vision_tools.StrOutputParser.ainvoke",
        new_callable=AsyncMock
    ) as mock_invoke:
        mock_invoke.return_value = '{"score": "4/5", "explanation": "Bold vision"}'

        data_package = {
            "vision_data": {"category_play": {"definition": "AI SaaS"}},
            "market_analysis": {},
            "contradiction_report": "None",
            "risk_report": "None"
        }
        result = await vision_scoring_agent(data_package)

        assert result["score"] == "4/5"
        assert result["explanation"] == "Bold vision"
        assert result["score_numeric"] == 80  # 4/5 * 20


@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.vision_tools.get_llm")
async def test_vision_risk_agent(mock_get_llm):
    """vision_risk_agent returns the raw LLM string output."""
    with patch(
        "app.graph.evaluation_agent.tools.vision_tools.StrOutputParser.ainvoke",
        new_callable=AsyncMock
    ) as mock_invoke:
        mock_invoke.return_value = "Key risk: market timing."

        result = await vision_risk_agent(
            {"category_play": {"definition": "AI SaaS"}},
            {"trend": "growing"},
            "Analyse vision risks: {vision_data} {market_analysis}"
        )

        assert result == "Key risk: market timing."
        mock_invoke.assert_called_once()


@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.vision_tools.get_llm")
@patch(
    "app.graph.evaluation_agent.tools.vision_tools.get_market_signals_serper",
    new_callable=AsyncMock
)
async def test_analyze_category_future(mock_signals, mock_get_llm):
    """analyze_category_future fetches market signals then calls LLM."""
    mock_signals.return_value = "AI SaaS market is booming."

    with patch(
        "app.graph.evaluation_agent.tools.vision_tools.StrOutputParser.ainvoke",
        new_callable=AsyncMock
    ) as mock_invoke:
        mock_invoke.return_value = '{"trend": "Bullish", "score": "5/5"}'

        vision_data = {
            "category_play": {"definition": "AI SaaS", "moat": "Data Network"},
            "customer_obsession": {"problem_statement": "Founders lack validation tools"}
        }
        result = await analyze_category_future(vision_data)

        assert result["trend"] == "Bullish"
        mock_signals.assert_awaited_once_with(vision_data)


# --- BUSINESS ---

@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.business_tools.get_llm")
async def test_business_scoring_agent(mock_get_llm):
    """business_scoring_agent picks the Pre-Seed template and parses score."""
    with patch(
        "app.graph.evaluation_agent.tools.business_tools.StrOutputParser.ainvoke",
        new_callable=AsyncMock
    ) as mock_invoke:
        mock_invoke.return_value = '{"score": "3/5", "explanation": "Decent model"}'

        data_package = {
            "business_data": {"context": {"stage": "Pre-Seed"}},
            "calculator_report": {},
            "contradiction_report": "None",
            "risk_report": "None"
        }
        result = await business_scoring_agent(data_package)

        assert result["score"] == "3/5"
        assert result["score_numeric"] == 60  # 3/5 * 20
        assert result["explanation"] == "Decent model"


@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.business_tools.get_llm")
async def test_business_risk_agent(mock_get_llm):
    """business_risk_agent returns the raw LLM risk string."""
    with patch(
        "app.graph.evaluation_agent.tools.business_tools.StrOutputParser.ainvoke",
        new_callable=AsyncMock
    ) as mock_invoke:
        mock_invoke.return_value = "Risk: High burn rate."

        result = await business_risk_agent(
            {"context": {"stage": "Pre-Seed"}},
            "Assess business risks: {business_data}"
        )

        assert result == "Risk: High burn rate."
        mock_invoke.assert_called_once()


# --- GTM ---

@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.gtm_tools.get_llm")
async def test_gtm_scoring_agent(mock_get_llm):
    """gtm_scoring_agent routes by stage and correctly parses score."""
    with patch(
        "app.graph.evaluation_agent.tools.gtm_tools.StrOutputParser.ainvoke",
        new_callable=AsyncMock
    ) as mock_invoke:
        mock_invoke.return_value = '{"score": "4/5", "explanation": "Solid GTM"}'

        gtm_data = {"context": {"stage": "Pre-Seed"}}
        result = await gtm_scoring_agent(
            gtm_data=gtm_data,
            economics_report={"conversion_rate": 10.0},
            contradiction_report="None",
            risk_report="None"
        )

        assert result["score"] == "4/5"
        assert result["score_numeric"] == 80
        assert result["explanation"] == "Solid GTM"


@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.gtm_tools.get_llm")
async def test_gtm_risk_agent(mock_get_llm):
    """gtm_risk_agent returns raw LLM string for the given template."""
    with patch(
        "app.graph.evaluation_agent.tools.gtm_tools.StrOutputParser.ainvoke",
        new_callable=AsyncMock
    ) as mock_invoke:
        mock_invoke.return_value = "GTM risk: Channel saturation."

        result = await gtm_risk_agent(
            {"context": {"stage": "Pre-Seed"}},
            "Assess GTM risks: {gtm_json}"
        )

        assert result == "GTM risk: Channel saturation."
        mock_invoke.assert_called_once()


# --- OPERATIONS ---

@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.operations_tools.get_llm")
async def test_operations_scoring_agent(mock_get_llm):
    """operations_scoring_agent parses score and attaches score_numeric."""
    with patch(
        "app.graph.evaluation_agent.tools.operations_tools.StrOutputParser.ainvoke",
        new_callable=AsyncMock
    ) as mock_invoke:
        mock_invoke.return_value = '{"score": "2/5", "explanation": "Ops needs work"}'

        data_package = {
            "operations_data": {},
            "benchmarks": "Seed median round: $2M",
            "contradiction_report": "None",
            "risk_report": "None"
        }
        result = await operations_scoring_agent(data_package)

        assert result["score"] == "2/5"
        assert result["score_numeric"] == 40  # 2/5 * 20
        assert result["explanation"] == "Ops needs work"


@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.operations_tools.get_llm")
async def test_operations_risk_agent(mock_get_llm):
    """operations_risk_agent returns the raw LLM risk assessment string."""
    with patch(
        "app.graph.evaluation_agent.tools.operations_tools.StrOutputParser.ainvoke",
        new_callable=AsyncMock
    ) as mock_invoke:
        mock_invoke.return_value = "Ops risk: Key-person dependency."

        result = await operations_risk_agent(
            operations_data={"context": {"stage": "Pre-Seed"}},
            benchmarks="Seed median: $2M",
            template="Assess ops risks: {operations_data} {benchmarks}"
        )

        assert result == "Ops risk: Key-person dependency."
        mock_invoke.assert_called_once()


# --- PRODUCT ---

@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.product_tools.get_llm")
async def test_product_scoring_agent(mock_get_llm):
    """product_scoring_agent parses score from LLM and returns score_numeric."""
    with patch(
        "app.graph.evaluation_agent.tools.product_tools.StrOutputParser.ainvoke",
        new_callable=AsyncMock
    ) as mock_invoke:
        mock_invoke.return_value = '{"score": "5/5", "explanation": "Excellent product"}'

        data_package = {
            "internal_data": {"product_and_solution": {}},
            "contradiction_report": "None",
            "risk_report": "None",
            "tech_stack_report": "React, Node",
            "visual_analysis_report": "Clean UI"
        }
        result = await product_scoring_agent(data_package)

        assert result["score"] == "5/5"
        assert result["score_numeric"] == 100
        assert result["explanation"] == "Excellent product"


# --- TRACTION ---

@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.traction_tools.get_llm")
async def test_traction_scoring_agent(mock_get_llm):
    """traction_scoring_agent routes by stage and parses score correctly."""
    with patch(
        "app.graph.evaluation_agent.tools.traction_tools.StrOutputParser.ainvoke",
        new_callable=AsyncMock
    ) as mock_invoke:
        mock_invoke.return_value = '{"score": "3/5", "explanation": "Early traction present"}'

        data_package = {
            "traction_data": {"context": {"stage": "Pre-Seed"}},
            "contradiction_report": "None",
            "risk_report": "None"
        }
        result = await traction_scoring_agent(data_package)

        assert result["score"] == "3/5"
        assert result["score_numeric"] == 60  # 3/5 * 20
        assert result["explanation"] == "Early traction present"


@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.traction_tools.get_llm")
async def test_traction_risk_agent(mock_get_llm):
    """traction_risk_agent returns the raw LLM traction risk string."""
    with patch(
        "app.graph.evaluation_agent.tools.traction_tools.StrOutputParser.ainvoke",
        new_callable=AsyncMock
    ) as mock_invoke:
        mock_invoke.return_value = "Traction risk: Concentrated in one channel."

        result = await traction_risk_agent(
            {"context": {"stage": "Pre-Seed"}, "validation_signals": {}},
            "Assess traction risks: {traction_json}"
        )

        assert result == "Traction risk: Concentrated in one channel."
        mock_invoke.assert_called_once()


# --- PROBLEM (loaded risk check) ---

@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.tools.problem_tools.get_llm")
async def test_loaded_risk_check_with_search(mock_get_llm):
    """loaded_risk_check_with_search passes combined data to LLM and returns string."""
    with patch(
        "app.graph.evaluation_agent.tools.problem_tools.StrOutputParser.ainvoke",
        new_callable=AsyncMock
    ) as mock_invoke:
        mock_invoke.return_value = "Risk: Problem is not urgent enough for paid solutions."

        problem_data = {"problem_statement": "Manual testing"}
        search_results = {"pain_validation_search": [{"title": "Hit", "snippet": "Real pain."}]}
        agent_prompt = "Assess problem risks: {internal_json} {external_search_json}"

        result = await loaded_risk_check_with_search(problem_data, search_results, agent_prompt)

        assert result == "Risk: Problem is not urgent enough for paid solutions."
        mock_invoke.assert_called_once()


# ==========================================
# 4. FINAL SCORING AGENT TESTS
# ==========================================

def test_calculate_weighted_score_pre_seed():
    """calculate_weighted_score applies pre-seed weights and returns correct verdict band."""
    from app.graph.evaluation_agent.node import calculate_weighted_score

    # All dimensions at 80 (4/5)
    scores = {k: 80 for k in ["team", "problem", "product", "market", "traction", "gtm", "business", "vision", "operations"]}
    _, weighted_total, verdict, rubric_5 = calculate_weighted_score(scores, "Pre-Seed")

    # Each rubric_5 value = 80/20 = 4.0
    assert rubric_5["team"] == 4.0
    # Weighted total must be above 0
    assert weighted_total > 0
    # At 4/5 across the board, the weighted total should be well above 26 → at least "Invest"
    assert verdict in {"Invest (Team Conviction)", "Strong Invest", "Extremely Good"}


def test_calculate_weighted_score_low_scores():
    """calculate_weighted_score maps very low scores to 'Pass (Not Ready)' verdict."""
    from app.graph.evaluation_agent.node import calculate_weighted_score

    scores = {k: 20 for k in ["team", "problem", "product", "market", "traction", "gtm", "business", "vision", "operations"]}
    _, weighted_total, verdict, _ = calculate_weighted_score(scores, "Pre-Seed")

    assert verdict == "Pass (Not Ready)"
    assert weighted_total < 20


@pytest.mark.asyncio
@patch("app.graph.evaluation_agent.node.get_llm")
async def test_final_node_builds_report(mock_get_llm):
    """final_node assembles scores, calls LLM, and returns a final_report dict."""
    from app.graph.evaluation_agent.node import final_node

    # Build a minimal state: each *_report has score_numeric=80
    dims = ["team", "problem", "product", "market", "traction", "gtm", "business", "vision", "operations"]
    state = {
        "user_data": {
            "startup_evaluation": {
                "company_snapshot": {"current_stage": "Pre-Seed"}
            }
        },
        "t5_deep_insight": "Good startup potential.",
        **{
            f"{k}_report": {
                "score_numeric": 80,
                "explanation": f"{k} looks good",
                "confidence_level": "High",
                "green_flags": [],
                "red_flags": []
            }
            for k in dims
        }
    }

    # Mock the LLM chain to return a valid final JSON structure
    mock_chain_result = {
        "investor_output": {
            "scorecard_grid": {},
            "weighted_score": 40.0,
            "verdict": "Strong Invest"
        },
        "founder_output": {
            "scorecard_grid": {},
            "weighted_score": 40.0,
            "verdict": "Strong Invest",
            "dimension_analysis": []
        }
    }

    mock_llm_instance = MagicMock()
    mock_get_llm.return_value = mock_llm_instance

    with patch("app.graph.evaluation_agent.node.JsonOutputParser.ainvoke", new_callable=AsyncMock) as mock_parser:
        mock_parser.return_value = mock_chain_result

        result = await final_node(state)

    assert "final_report" in result
    final = result["final_report"]
    # After backfill, investor_output must contain a verdict
    assert "verdict" in final.get("investor_output", final.get("investor_output", {}))
