import sys, os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.graph.market_research_agent.workflow import market_research_app
from app.core.logger import get_logger
import sys

# Force UTF-8 encoding for console output to handle emojis
sys.stdout.reconfigure(encoding='utf-8')

logger = get_logger("MarketResearchVerifier")

if __name__ == "__main__":
    logger.info("[LAUNCH] Verifying Granular Market Research Agent...")
    
    initial_state = {
        "input_idea": "ai app to help startups",
        "input_problem": "people with udeas dont know where to validate it and how to organize and gather info they need"
    }
    
    try:
        # Stream the output to see individual node execution
        for event in market_research_app.stream(initial_state):
            for key, value in event.items():
                logger.info(f"\n[SUCCESS] Node '{key}' finished.")
                if not isinstance(value, str):
                    logger.info(f"   Output: {value}")
        
        logger.info("\n[CELEBRATE] Full Workflow Completed Successfully!")
    except Exception as e:
        logger.error(f"\n[ERROR] Execution Failed: {e}")
