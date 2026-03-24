# 1. Initialize the connection (use environment variables for security in production!)
from app.core.config import config
from app.graph.matching_agent.graph_db import RecommendationGraph
uri = config.NEO4J_URI
user = config.NEO4J_USERNAME
password = config.NEO4J_PASSWORD



graph_db = RecommendationGraph(uri, user, password)

# --- Simulating adding data (e.g., from your Supabase webhooks) ---

# Adding the first pitch from your Supabase data
pitch_tags = {
    "Consumer & Commerce": ["Marketplace"], 
    "Specialized Industry Tech": ["Proptech"]
}
graph_db.add_pitch_tags("0011b18a...", pitch_tags)

# Adding the first investor from your Supabase data
investor_tags = ["Tech", "AI"] # If they had initial tags
graph_db.add_investor("17fbb93e-d8f8-433b-acb8-1d532d43976a", investor_tags)


# --- Retrieving the data for your matching logic ---

# Get the sub-tags for that specific investor
recommended_subtags = graph_db.get_investor_subtags("17fbb93e-d8f8-433b-acb8-1d532d43976a")

print("Sub-tags to prioritize for this investor:")
print(recommended_subtags)
# Output will look like: [{'sub_tag': 'Marketplace', 'parent_tag': 'Consumer & Commerce', 'weight': 1.0}, ...]

# Close the connection when the app shuts down
graph_db.close()