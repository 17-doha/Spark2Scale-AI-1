from app.graph.feed_recommedation_agent.tools.tag_tools import get_investor_subtags

# We set the hate threshold to 0.15 (15%)
results = get_investor_subtags("6622ce4d-2f0d-4791-9b80-867d69e6c9a9", hate_threshold=0.15)

print("Final Ordered SubTags:", results)