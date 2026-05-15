from locust import HttpUser, task, between
import json

class FastAPIAgentUser(HttpUser):
    wait_time = between(1, 5) # Simulate user think time

    @task(1)
    def test_health_check(self):
        self.client.get("/")

    @task(2)
    def test_chat_endpoint(self):
        headers = {'Content-Type': 'application/json'}
        
        # USE THE CORRECT SCHEMA PAYLOAD
        payload = {
            "user_message": "What should be my main focus for marketing this app?",
            "chat_history": [
                {
                    "role": "user",
                    "content": "Hi, I am building an AI pet care app."
                },
                {
                    "role": "assistant",
                    "content": "That sounds great! Who is your target audience?"
                }
            ],
            "startup_data": {
                "data": {
                    "startup_evaluation": {
                        "company_snapshot": {
                            "idea_name": "PetCare AI",
                            "target_audience": "First-time pet owners"
                        }
                    }
                }
            }
        }
        
        # Using the correct path: /api/v1/chat/chat
        with self.client.post("/api/v1/chat/chat", data=json.dumps(payload), headers=headers, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 429:
                response.failure("Rate Limited! (SlowAPI triggered)")
            else:
                # Capture the actual error text if it fails again to see exactly what FastAPI complained about
                response.failure(f"Failed with {response.status_code}: {response.text}")