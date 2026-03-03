import os
import sys

# Add the project directory to sys path so we can import the app modules
project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_dir)

from app.graph.document_generator.swot.scraper import scrape_competitor_reviews
from app.graph.document_generator.swot.gap_analyzer import analyze_competitive_gap
from app.graph.document_generator.swot.regulatory_and_barrier_node import scrape_regulatory_barriers
from app.graph.document_generator.swot.synthesizer import synthesize_swot_matrix
from app.graph.document_generator.tools import generate_swot_document
from dotenv import load_dotenv
import logging

# Set up logging for the test
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestSWOT")

load_dotenv()

def run_swot_pipeline(idea_name: str):
    logger.info(f"--- Starting Full SWOT Pipeline for: '{idea_name}' ---")
    
    # Step 1: Run the new scraper
    logger.info("\n--- STEP 1: Scraping Competitor Reviews ---")
    reviews_file = scrape_competitor_reviews(idea_name)
    if not reviews_file:
        logger.warning("No reviews file generated. Missing competitors data or Serper API error.")
    else:
        logger.info(f"Competitor reviews saved to: {reviews_file}")
        
    # Step 2: Run the Gap Analyzer LLM
    logger.info("\n--- STEP 2: Analyzing Competitive Market Gaps ---")
    description = "An AI-powered app that quickly and accurately validates startup ideas, finding market gaps so founders don't waste time."
    gap_file = analyze_competitive_gap(idea_name, description)
    if not gap_file:
         logger.warning("No competitive gap file generated.")
    else:
         logger.info(f"Competitive gap analysis saved to: {gap_file}")
         
    # Step 3: Run the PEST Regulatory Scraper
    logger.info("\n--- STEP 3: Scraping Regulatory Barriers ---")
    barriers_file = scrape_regulatory_barriers(idea_name, "Global")
    if not barriers_file:
         logger.warning("No barriers file generated.")
    else:
         logger.info(f"Regulatory barriers saved to: {barriers_file}")
         
    # Step 4: Run the TOWS Synthesizer
    logger.info("\n--- STEP 4: Synthesizing TOWS Matrix Verdict ---")
    tows_file = synthesize_swot_matrix(idea_name)
    if not tows_file:
         logger.warning("No TOWS matrix file generated.")
    else:
         logger.info(f"TOWS matrix saved to: {tows_file}")
         
    # Step 5: Generate the document (which will pick up all data)
    logger.info("\n--- STEP 5: Generating Final SWOT Document ---")
    try:
        output = generate_swot_document(idea_name)
        logger.info("\n--- generation completed ---")
        print("\n\n" + "="*50)
        print("GENERATED SWOT DOCUMENT:")
        print("="*50)
        print(output)
        print("="*50 + "\n")
    except Exception as e:
        logger.error(f"Failed to generate SWOT document: {e}")

if __name__ == "__main__":
    # Test with the existing idea name that has data in data_output
    test_idea = "ai app to help startups"
    
    if len(sys.argv) > 1:
        test_idea = " ".join(sys.argv[1:])
        
    run_swot_pipeline(test_idea)
