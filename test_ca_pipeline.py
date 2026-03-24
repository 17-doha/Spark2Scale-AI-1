import asyncio
import json
from app.graph.document_generator.workflow import document_generator_app

async def test_workflow():
    print("=== Testing Competitor Analysis Pipeline Full ===")
    
    try:
        with open("data_output/ai_app_to_help_startups_Market_Report.json", "r", encoding="utf-8") as f:
            mr_json = json.load(f)
    except Exception as e:
        print(f"Failed to load JSON: {e}")
        return
        
    ca_state = {
        "document_type": "competitor_analysis",
        "idea_name": "AI Pet Care App",
        "idea_description": "An AI-powered app to help novice pet owners with care, training, and nutrition.",
        "region": "Global",
        "market_research": mr_json
    }
    
    print("Invoking graph...")
    try:
        ca_result = await document_generator_app.ainvoke(ca_state)
        print("\n[Competitor Analysis Run Complete]")
        doc = ca_result.get("competitor_analysis_document")
        if doc:
            print("\n----- GENERATED MARKDOWN -----\n")
            print(doc.get("markdown", "NO MARKDOWN FOUND"))
            print("\n------------------------------\n")
        else:
            print("\nNO DOC PRODUCED")
    except Exception as e:
        print(f"\n[ERROR] Pipeline failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_workflow())
