import sys, os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import requests
import json
import os

API_URL = "http://127.0.0.1:8000/api/v1/swot/generate"

def test_swot_api():
    print("Testing SWOT Generation API endpoint...")
    
    # 1. Load an existing actual market report to send as the payload body
    report_path = "data_output/ai_app_to_help_startups_Market_Report.json"
    
    if not os.path.exists(report_path):
        print(f"Error: Could not find '{report_path}'.")
        return
        
    with open(report_path, "r", encoding="utf-8") as f:
        market_research_data = json.load(f)
        
    # 2. Construct the SWOTRequest payload schema
    payload = {
        "idea_name": "ai app to help startups",
        "idea_description": market_research_data.get("executive_summary", "Validating startup ideas."),
        "region": "Global",
        "market_research": market_research_data,
        "comment": "i think the weakness should be more about the idea itself not the market"
    }
    
    print(f"Sending POST request to {API_URL}...")
    
    try:
        # 3. Hit the API endpoint
        response = requests.post(API_URL, json=payload, timeout=300) # SWOT generation is slow, tall timeout
        
        print(f"\nStatus Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("\n✅ SUCCESS! Received SWOT Response:")
            print(f"Message: {result.get('message')}")
            
            if result.get("errors"):
                 print("Errors occurred during execution:")
                 for err in result["errors"]:
                     print(f" - {err}")
                     
            if result.get("swot_document"):
                 print("\n--- SWOT Document Snippet ---")
                 # Print just the strengths to verify it worked and save console space
                 print("Strengths:", result["swot_document"].get("strengths", []))
                 print("-----------------------------\n")
        else:
            print(f"❌ Failed. API returned error: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Failed to connect to the server. Did you start the FastAPI server with `python main.py`?")
    except Exception as e:
         print(f"❌ An error occurred: {e}")

if __name__ == "__main__":
    test_swot_api()
