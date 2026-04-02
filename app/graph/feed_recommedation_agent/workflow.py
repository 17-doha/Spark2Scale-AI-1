"""
Feed Recommendation Agent — LangGraph Workflow
===============================================
fetch_tags → embed → store  (sequential pipeline)
"""
from langgraph.graph import StateGraph, START, END
from app.graph.feed_recommedation_agent.state import FeedRecommendationState
from app.graph.feed_recommedation_agent.node import fetch_tags_node, embed_node, store_node


def create_feed_recommendation_graph():
    wf = StateGraph(FeedRecommendationState)

    wf.add_node("fetch_tags", fetch_tags_node)
    wf.add_node("embed",      embed_node)
    wf.add_node("store",      store_node)

    wf.add_edge(START,         "fetch_tags")
    wf.add_edge("fetch_tags",  "embed")
    wf.add_edge("embed",       "store")
    wf.add_edge("store",       END)

    return wf.compile()


feed_recommendation_app = create_feed_recommendation_graph()