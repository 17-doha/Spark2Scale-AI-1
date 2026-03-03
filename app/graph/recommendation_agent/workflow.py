from .schema import StartupData
from .helpers import extract_key_insights
from .patterns import detect_patterns
from .tools import run_market_intel
from .node import AgentNodes
from app.core.config import Config
from app.utils.output_manager import OutputManager
from app.utils.logger import logger
import time

def run_recommendation_agent(raw_input, eval_output, api_key, save_output=True, request_id=None):
    """
    Run the recommendation agent workflow
    
    Args:
        raw_input: Raw startup input data
        eval_output: Evaluation output data
        api_key: Gemini API key
        save_output: Whether to save output to files (default: True)
        request_id: Optional request ID for tracking
        
    Returns:
        tuple: (final_report, output_paths) or just final_report if save_output=False
    """
    start_time = time.time()
    logger.info(f"Starting recommendation agent workflow for request_id: {request_id}")
    # 1. Parse & Validate
    data = StartupData(**eval_output)
    insights = extract_key_insights(raw_input)
    
    # 2. Convert Pydantic scores to dict format for pattern detection
    # Pattern detection expects: scores['team']['score'] and scores['team']['description']
    scores_dict = data.scores.model_dump()
    
    # 3. Deterministic Analysis
    matched_patterns = detect_patterns(scores_dict)
    
    # 4. AI Nodes
    agent = AgentNodes(api_key)
    replacements = agent.improve_statements(insights)
    
    # Run market intelligence before synthesis
    market_signals = run_market_intel(insights, tavily_api_key=Config.TAVILY_API_KEY)
    
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

