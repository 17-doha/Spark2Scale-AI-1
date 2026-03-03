import os
import json
import asyncio
from app.graph.recommendation_agent.workflow import run_recommendation_agent
from app.core.config import Config
from app.utils.logger import logger

def test_recommendation_agent():
    """
    Test script to verify the recommendation agent runs end-to-end.
    It passes mock data that should trigger cross-category patterns and World Bank/Tavily signals.
    """
    # 1. Setup mock raw input (Mimicking the start of a real pipeline)
    print("Initializing test for Recommendation Agent...")
    
    mock_raw_input = {
        "startup_evaluation": {
            "company_snapshot": {
                "company_name": "MENA Fintech Nexus",
                "current_stage": "Seed",
                "current_round": {"target_amount": "$500k"},
                "country": "Egypt",
                "sector": "Fintech"
            },
            "problem_definition": {
                "problem_statement": "SMEs lack access to credit",
                "evidence": {"customer_quotes": ["We can't get loans."]},
                "gap_analysis": "Existing banks are too slow."
            },
            "founder_and_team": {
                "founders": [
                    {
                        "prior_experience": "10 years in banking",
                        "founder_market_fit_statement": "Deep domain expertise"
                    }
                ]
            },
            "product_and_solution": {
                "differentiation": "AI-driven credit scoring",
                "core_stickiness": "Integrated with accounting software"
            },
            "traction_metrics": {
                "early_revenue": "USD 5000",
                "active_users_monthly": 100
            },
            "vision_and_strategy": {
                "five_year_vision": "Dominant SME lender in MENA"
            },
            "market_and_scope": {
                "beachhead_market": "Egyptian retail SMEs"
            }
        }
    }

    # 2. Setup mock evaluation output
    mock_eval_output = {
        "stage": "Seed",
        "company_context": "B2B SaaS Fintech in Egypt",
        "scores": {
            "team": {"score": 2.0, "description": "Solo founder not selling, missing tech lead."},
            "problem": {"score": 3.0, "description": "Clear problem but vague customer language."},
            "product": {"score": 4.0, "description": "Solid MVP."},
            "market": {"score": 3.0, "description": "Fragmented customer base."},
            "traction": {"score": 2.0, "description": "Spiky metrics, lots of signups but unknown retention."},
            "gtm": {"score": 2.0, "description": "Founder relying on marketing, not selling directly."},
            "economics": {"score": 5.0, "description": "Good margins."},
            "vision": {"score": 2.0, "description": "Constant narrative change."},
            "ops": {"score": 3.0, "description": "No weekly planning."}
        }
    }

    print("\n--- Running the Workflow ---")
    try:
        # Check API Keys
        if not Config.GEMINI_API_KEY:
            print("[Warning] GEMINI_API_KEY is not set in config/environments! The AI Node generation might fail.")
            
        if not Config.TAVILY_API_KEY:
             print("[Notice] TAVILY_API_KEY is not set. Market Intelligence will fallback to World Bank only (which is fine).")
             
        # Run workflow
        result = run_recommendation_agent(
            raw_input=mock_raw_input,
            eval_output=mock_eval_output,
            api_key=Config.GEMINI_API_KEY,
            save_output=True, # Generate the actual markdown file output
            request_id="test-recommendation-123"
        )
        
        print("\n--- Workflow Execution Successful! ---")
        
        # 3. Verify specifically the new intermediate structures
        market_signals = result.get("market_signals", {})
        print("\n--- Market Signals ---")
        print(f"Overall Confidence: {market_signals.get('confidence', 'N/A')}")
        print(f"Funding Climate: {market_signals.get('funding_climate', 'N/A')}")
        print(f"Risk Flags Found: {len(market_signals.get('risk_flags', []))}")
        for flag in market_signals.get("risk_flags", []):
             print(f"  - {flag}")

        patterns = result.get("matched_patterns", [])
        print(f"\n--- Matched Patterns with Cross-Category Confidence ({len(patterns)}) ---")
        for i, p in enumerate(patterns[:5]): # Show top 5
             print(f"{i+1}. ID: {p.get('pattern_id')} | Category: {p.get('pattern_id', '').split('-')[1] if p.get('pattern_id') else 'N/A'} | Severity: {p.get('severity', 'N/A')}")
             print(f"   Name: {p.get('name')}")
             print(f"   Confidence: {p.get('confidence')} ({p.get('confidence_reasoning')})")
             print(f"   Strength Score: {p.get('strength_score')} ({p.get('strength_label')})")
             
        print("\n--- Refining Statements Result ---")
        refs = result.get("refined_statements", {})
        if refs:
            print("Successfully refined statements.")
        else:
            print("No refined statements returned (possibly hit rate limits on Gemini API).")
            
        final_report = result.get("final_report", "")
        if final_report:
             print("\n--- Final Report Outline Snippet ---")
             print(final_report[:500] + "...\n")
             print(f"[Total generation complete: {len(final_report)} characters]")
             
        paths = result.get("output_paths", {})
        if paths:
             print(f"\nReport successfully saved to: {paths.get('folder', 'unknown directory')}")
             
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n[Error] The workflow failed: {e}")

if __name__ == "__main__":
    test_recommendation_agent()
