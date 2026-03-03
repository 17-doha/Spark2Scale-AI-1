import os
import sys
import json
import logging
from pprint import pprint

# Add the project directory to sys path so we can import the app modules
project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "."))
sys.path.append(project_dir)

from app.graph.document_generator.workflow import document_generator_app
from dotenv import load_dotenv

# Set up logging for the test
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestDocGenGraph")

load_dotenv()

def test_document_generator(idea_name: str):
    logger.info(f"--- Testing Document Generator Workflow for: '{idea_name}' ---")
    
    # 1. Load the mock market research data
    clean_name = idea_name.replace(' ', '_').replace('"', '').replace("'", "")
    report_path = f"data_output/{clean_name}_Market_Report.json"
    
    if not os.path.exists(report_path):
        logger.error(f"Market report not found: {report_path}")
        return
        
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            market_research = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load market report: {e}")
        return
        
    # 2. Prepare the initial state
    initial_state = {
        "idea_name": idea_name,
        "idea_description": market_research.get("executive_summary", "An AI-powered app that quickly and accurately validates startup ideas, finding market gaps so founders don't waste time."),
        "region": "Global",
        "market_research": market_research
    }
    
    # 3. Invoke the graph
    logger.info("--- Invoking Graph ---")
    try:
        final_state = document_generator_app.invoke(initial_state)
        
        logger.info("--- Graph Execution Completed ---")
        
        if final_state.get("errors"):
             logger.error("Errors encountered during execution:")
             for err in final_state.get("errors", []):
                 logger.error(f" - {err}")
        else:
            logger.info("No errors encountered.")
            print("\n" + "="*50)
            print("FINAL GENERATED SWOT DOCUMENT SNIPPET:")
            print("="*50)
            swot_doc = final_state.get("swot_document", {})
            pprint(swot_doc)
            print("="*50 + "\n")
    except Exception as e:
        import traceback
        with open("error.txt", "w") as f:
            f.write(traceback.format_exc())
        logger.error(f"Graph execution failed. See error.txt for traceback. Message: {e}")

if __name__ == "__main__":
    # Test with the existing idea name that has data in data_output
    test_idea = "ai app to help startups"
    
    if len(sys.argv) > 1:
        test_idea = " ".join(sys.argv[1:])
        
    test_document_generator(test_idea)
