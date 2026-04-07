import requests
import time

# Point to your local FastAPI server
URL = "http://localhost:8000/api/interactions"

# 1. Provide real IDs from your database for the test
payload = {
    "user_id": "6622ce4d-2f0d-4791-9b80-867d69e6c9a9",
    "pitch_id": "81f39c03-e78f-4015-9628-a333d8d4a28c", # Must exist in Supabase!
    "liked": True,
    "contacted": False
}

print(f"Sending Interaction: {payload['liked']=}, {payload['contacted']=}")

# 2. Fire the request
response = requests.post(URL, json=payload)

# 3. Print the immediate HTTP response
print(f"Status Code: {response.status_code}")
print(f"Response Body: {response.json()}")

print("Waiting 2 seconds to let background Neo4j tasks finish...")
time.sleep(2)
print("Done! Check your FastAPI terminal to see the Neo4j logs.")