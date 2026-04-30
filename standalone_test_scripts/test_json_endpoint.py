import sys, os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import requests
import json

url = "http://localhost:8000/api/v1/competitor-matrix/generate"

try:
    with open("data_output/ai_app_to_help_startups_Market_Report.json", "r", encoding="utf-8") as f:
        mr_json = json.load(f)
except Exception as e:
    print(f"Failed to load Market Report JSON: {e}")
    mr_json = {"data": "dummy"}

payload = {
    "idea_name": "AI Pet Care App",
    "idea_description": "An AI-powered app to help novice pet owners with care, training, and nutrition.",
    "region": "Global",
    "market_research": mr_json
}

headers = {"Content-Type": "application/json"}

print(f"Sending request to {url} (this make take a few minutes)...")
response = requests.post(url, json=payload, headers=headers)

if response.status_code == 200:
    print("Success! JSON payload snippet:")
    data = response.json()
    print(json.dumps(data, indent=2)[:1500] + "\n... (truncated)")
else:
    print(f"Error: {response.status_code}\n{response.text}")
