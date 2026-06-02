from .schema import StartupData
from .helpers import extract_key_insights, fetch_startup_evaluation_from_db
from .patterns import detect_patterns
from .tools import run_market_intel
from .node import AgentNodes
from app.core.config import Config
from app.utils.output_manager import OutputManager
from app.utils.logger import logger
import time

def run_recommendation_agent(raw_input, eval_output, api_key, save_output=True, request_id=None, startup_id=None):
    """
    Run the recommendation agent workflow

    Args:
        raw_input: Raw startup input data
        eval_output: Evaluation output data
        api_key: Gemini API key
        save_output: Whether to save output to files (default: True)
        request_id: Optional request ID for tracking
        startup_id: Optional Supabase startup id. When provided, the complete
            evaluation document is loaded from the DB (like the other documents
            do) and used as the source for insight extraction, instead of the
            partial raw_input that the caller sends.

    Returns:
        tuple: (final_report, output_paths) or just final_report if save_output=False
    """
    start_time = time.time()
    logger.info(f"Starting recommendation agent workflow for request_id: {request_id}")
    # 1. Parse & Validate
    data = StartupData(**eval_output)

    # Prefer the full, enriched evaluation stored in the DB. The /recommend
    # payload's raw_input is frequently a partial early submission, which left
    # statements (differentiation, vision, beachhead, gap analysis, founder
    # fit, …) empty — rendering as "None" in the report. Fall back to the
    # passed raw_input whenever the DB fetch yields nothing.
    insights_source = raw_input
    if startup_id:
        db_eval = fetch_startup_evaluation_from_db(startup_id)
        if db_eval:
            insights_source = db_eval

    insights = extract_key_insights(insights_source)
    
    # 2. Convert Pydantic scores to dict format for pattern detection
    # Pattern detection expects: scores['team']['score'] and scores['team']['description']
    scores_dict = data.scores.model_dump()

    # Weakest evaluation pillar — drives the targeted multi-source intel search.
    lowest_category = min(scores_dict, key=lambda k: scores_dict[k].get("score", 5))

    # 3. Deterministic Analysis (stage-aware: late-stage weaknesses weigh heavier)
    matched_patterns = detect_patterns(scores_dict, stage=data.stage)
    
    # 4. AI Nodes
    agent = AgentNodes(api_key)
    replacements = agent.improve_statements(insights)

    # 4b. Fallback: improve_statements returns None when Gemini hits a 429
    # quota error. Without this, the "Statement Refinements" page would
    # silently disappear for some startups — making reports structurally
    # inconsistent. Build a passthrough from the real insights so the
    # section ALWAYS renders, agent-sourced, for every startup.
    if not replacements:
        logger.warning(
            "Refined statements unavailable (model quota) for request_id "
            f"{request_id}; using passthrough fallback from insights."
        )
        _fallback_why = (
            "Original retained — AI refinement was unavailable for this run "
            "(model quota). Regenerate for an enhanced version."
        )
        replacements = {
            key: {
                "original": str(insights.get(key, "N/A")),
                "recommended": str(insights.get(key, "N/A")),
                "why_better": _fallback_why,
            }
            for key in (
                "problem_statement",
                "founder_market_fit",
                "differentiation",
                "core_stickiness",
                "five_year_vision",
                "beachhead_market",
                "gap_analysis",
            )
        }
    
    # Run market intelligence before synthesis
    market_signals = run_market_intel(
        insights,
        tavily_api_key=Config.TAVILY_API_KEY,
        lowest_category=lowest_category,
        competitor=insights.get("top_competitor"),
    )
    
    final_report = agent.synthesize_report(data, matched_patterns, insights, replacements, market_signals)
    
    # 5. Store intermediate results in the data object (as part of internal state)
    data.insights = insights
    data.matched_patterns = matched_patterns
    data.refined_statements = replacements
    data.market_signals = market_signals
    
    # 6. Save output if requested
    output_paths = None
    if save_output:
        processing_time = time.time() - start_time
        output_manager = OutputManager()
        output_paths = output_manager.save_recommendation(
            recommendation_text=final_report,
            raw_input=raw_input,
            eval_output=eval_output,
            insights=insights,
            patterns=matched_patterns,
            refined_statements=replacements,  # Add refined statements
            market_signals=market_signals,
            request_id=request_id,
            processing_time=processing_time
        )
        logger.info(f"Output saved to: {output_paths['folder']}")
    
    end_time = time.time()
    processing_time = end_time - start_time
    logger.info(f"Recommendation agent workflow completed in {processing_time:.2f} seconds")
    
    return {
        "final_report": final_report,
        "output_paths": output_paths,
        "insights": insights,
        "matched_patterns": matched_patterns,
        "refined_statements": replacements,
        "market_signals": market_signals
    }

