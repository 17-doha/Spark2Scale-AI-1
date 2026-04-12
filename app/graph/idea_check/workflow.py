from langgraph.graph import StateGraph, START, END
from app.graph.idea_check.state import IdeaCheckState
from app.graph.idea_check.node import generate_queries_node, execute_search_node, analyze_pain_points_node

# Define Graph
builder = StateGraph(IdeaCheckState)

# Add Nodes
builder.add_node("generate_queries", generate_queries_node)
builder.add_node("execute_search", execute_search_node)
builder.add_node("analyze_pain_points", analyze_pain_points_node)

# Add Edges
builder.add_edge(START, "generate_queries")
builder.add_edge("generate_queries", "execute_search")
builder.add_edge("execute_search", "analyze_pain_points")
builder.add_edge("analyze_pain_points", END)

# Compile Graph
idea_check_app = builder.compile()
