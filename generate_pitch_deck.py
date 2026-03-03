"""
Generic Pitch Deck Generator - Premium Edition
Supports CSV or JSON input; auto-detects format and maps to presentation sections.
Uses the Multi-Agent LangGraph (Generator -> Recommender -> Refiner) for premium quality.
"""
import asyncio
import os
import logging
import time
from app.graph.ppt_generation_agent.tools.input_loader import load_input_directory
from app.api.routes.ppt_generation import run_ppt_generation, generate_deck_from_local_files
from app.graph.ppt_generation_agent.state import PPTGenerationState
from app.core.logger import get_logger

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = get_logger(__name__)

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "app", "graph", "ppt_generation_agent", "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "app", "graph", "ppt_generation_agent", "output")

async def main():
    print("=" * 60)
    print("PREMIUM PITCH DECK GENERATOR - MULTI-AGENT LOOP ACTIVE")
    print("=" * 60)
    
    try:
        print("\n⏳ Running Workflow via Shared Router Logic...")
        # Call the shared function directly. It handles loading, state creation, and graph execution.
        result = await generate_deck_from_local_files(OUTPUT_DIR)
        
        if result.get("status") == "success":
            print(f"\n✅ SUCCESS! Generated '{result.get('title')}'")
            print(f"📊 Iterations performed: {result.get('iterations')}")
            print(f"📁 Output File: {result.get('ppt_path')}")
        else:
            print(f"\n⚠️ Finished with unexpected status: {result}")

    except Exception as e:
        print(f"\n[ERROR] ERROR during generation: {e}")
        logger.error(f"Generation failed: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
