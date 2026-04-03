"""
app/graph/feed_recommedation_agent/workflow.py
"""

from langgraph.graph import StateGraph, START, END

from app.graph.feed_recommedation_agent.state import FilteredSearchState
from app.graph.feed_recommedation_agent.node import (
    generate_filter_tags_node,
    build_investor_vector_node,
    filtered_vector_search_node,
    rerank_candidates_node,
    format_output_node,
)


def _has_vector(state: FilteredSearchState) -> str:
    return "continue" if state.get("investor_vector") is not None else "end"


def _has_candidates(state: FilteredSearchState) -> str:
    return "continue" if state.get("candidates") else "end"


def create_filtered_search_graph():
    wf = StateGraph(FilteredSearchState)

    wf.add_node("generate_filter_tags",   generate_filter_tags_node)
    wf.add_node("build_investor_vector",  build_investor_vector_node)
    wf.add_node("filtered_vector_search", filtered_vector_search_node)
    wf.add_node("rerank_candidates",      rerank_candidates_node)
    wf.add_node("format_output",          format_output_node)

    wf.add_edge(START, "generate_filter_tags")
    wf.add_edge("generate_filter_tags", "build_investor_vector")

    wf.add_conditional_edges(
        "build_investor_vector",
        _has_vector,
        {"continue": "filtered_vector_search", "end": END},
    )
    wf.add_conditional_edges(
        "filtered_vector_search",
        _has_candidates,
        {"continue": "rerank_candidates", "end": END},
    )

    wf.add_edge("rerank_candidates", "format_output")
    wf.add_edge("format_output", END)

    return wf.compile()


filtered_search_app = create_filtered_search_graph()