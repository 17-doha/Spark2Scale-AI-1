from app.graph.market_research_agent.workflow import market_research_app
from app.graph.market_research_agent.logger_config import get_logger
import sys

# Force UTF-8 encoding for console output to handle emojis
sys.stdout.reconfigure(encoding='utf-8')

logger = get_logger("MarketResearchVerifier")

if __name__ == "__main__":
    logger.info("🚀 Verifying Granular Market Research Agent...")
    
    initial_state = {
        "input_idea": "new type of mobile phones",
        "input_problem": "a person need to reach people all over the world and this doesnt exist"
    }
    
    try:
        # Stream the output to see individual node execution
        for event in market_research_app.stream(initial_state):
            for key, value in event.items():
                logger.info(f"\n✅ Node '{key}' finished.")
                if not isinstance(value, str):
                    logger.info(f"   Output: {value}")
        
        logger.info("\n🎉 Full Workflow Completed Successfully!")
    except Exception as e:
        logger.error(f"\n❌ Execution Failed: {e}")
