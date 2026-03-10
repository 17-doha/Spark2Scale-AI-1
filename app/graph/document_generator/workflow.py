import logging
from langgraph.graph import StateGraph, START, END
from app.core.logger import get_logger
from .state import DocumentGeneratorState
from .nodes import (
    scrape_competitors_node,
    analyze_gaps_node,
    scrape_barriers_node,
    analyze_weaknesses_node,
    assemble_swot_context_node,
    synthesize_tows_node,
    generate_swot_node
)

logger = get_logger("DocumentGeneratorWorkflow")

def create_document_generator_workflow():
    """
    Creates the LangGraph workflow for Document Generation.
    Currently, this workflow executes the SWOT Pipeline.
    """
    workflow = StateGraph(DocumentGeneratorState)

    # 1. Add Nodes
    workflow.add_node("scrape_competitors", scrape_competitors_node)
    workflow.add_node("analyze_gaps", analyze_gaps_node)
    workflow.add_node("scrape_barriers", scrape_barriers_node)
    workflow.add_node("analyze_weaknesses", analyze_weaknesses_node)
    workflow.add_node("assemble_swot_context", assemble_swot_context_node)
    workflow.add_node("synthesize_tows", synthesize_tows_node)
    workflow.add_node("generate_swot", generate_swot_node)

    # 2. Add Edges (Logic Flow)
    # Executing sequentially to avoid LangGraph fan-in execution collisions 
    # and to reduce Gemini API rate limiting (429 Too Many Requests) under free tier.
    workflow.add_edge(START, "scrape_competitors")
    workflow.add_edge("scrape_competitors", "analyze_gaps")
    workflow.add_edge("analyze_gaps", "scrape_barriers")
    workflow.add_edge("scrape_barriers", "analyze_weaknesses")
    workflow.add_edge("analyze_weaknesses", "assemble_swot_context")
    workflow.add_edge("assemble_swot_context", "synthesize_tows")
    workflow.add_edge("synthesize_tows", "generate_swot")
    workflow.add_edge("generate_swot", END)

    # 3. Compile Workflow
    app = workflow.compile()
    
    return app

# Initialize the workflow graph when imported
document_generator_app = create_document_generator_workflow()
