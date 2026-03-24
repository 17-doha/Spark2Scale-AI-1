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
from .competitor_analysis_matrix.ca_nodes import (
    extract_competitors_from_market_research,
    enrich_competitor_links,
    enrich_market_intelligence,
    enrich_product_reality,
    classify_competitor_type,
    build_competitor_matrix
)

logger = get_logger("DocumentGeneratorWorkflow")

def create_document_generator_workflow():
    """
    Creates the LangGraph workflow for Document Generation.
    Currently, this workflow executes the SWOT Pipeline.
    """
    workflow = StateGraph(DocumentGeneratorState)

    # Routing Logic
    def route_document_type(state: DocumentGeneratorState) -> str:
        doc_type = state.get("document_type", "swot")
        if doc_type == "competitor_analysis":
            return "extract_competitors"
        return "scrape_competitors"

    # 1. Add Notes: SWOT Pipeline
    workflow.add_node("scrape_competitors", scrape_competitors_node)
    workflow.add_node("analyze_gaps", analyze_gaps_node)
    workflow.add_node("scrape_barriers", scrape_barriers_node)
    workflow.add_node("analyze_weaknesses", analyze_weaknesses_node)
    workflow.add_node("assemble_swot_context", assemble_swot_context_node)
    workflow.add_node("synthesize_tows", synthesize_tows_node)
    workflow.add_node("generate_swot", generate_swot_node)

    # 1. Add Nodes: Competitor Analysis Pipeline
    workflow.add_node("extract_competitors", extract_competitors_from_market_research)
    workflow.add_node("enrich_competitor_links", enrich_competitor_links)
    workflow.add_node("enrich_market_intelligence", enrich_market_intelligence)
    workflow.add_node("enrich_product_reality", enrich_product_reality)
    workflow.add_node("classify_competitor_type", classify_competitor_type)
    workflow.add_node("build_competitor_matrix", build_competitor_matrix)

    # 2. Add Edges (Logic Flow)
    # Executing sequentially to avoid LangGraph fan-in execution collisions 
    # and to reduce Gemini API rate limiting (429 Too Many Requests) under free tier.
    workflow.add_conditional_edges(START, route_document_type)
    
    # --- SWOT Edges ---
    workflow.add_edge("scrape_competitors", "analyze_gaps")
    workflow.add_edge("analyze_gaps", "scrape_barriers")
    workflow.add_edge("scrape_barriers", "analyze_weaknesses")
    workflow.add_edge("analyze_weaknesses", "assemble_swot_context")
    workflow.add_edge("assemble_swot_context", "synthesize_tows")
    workflow.add_edge("synthesize_tows", "generate_swot")
    workflow.add_edge("generate_swot", END)

    # --- Competitor Analysis Edges ---
    workflow.add_edge("extract_competitors", "enrich_competitor_links")
    workflow.add_edge("enrich_competitor_links", "enrich_market_intelligence")
    workflow.add_edge("enrich_market_intelligence", "enrich_product_reality")
    workflow.add_edge("enrich_product_reality", "classify_competitor_type")
    workflow.add_edge("classify_competitor_type", "build_competitor_matrix")
    workflow.add_edge("build_competitor_matrix", END)

    # 3. Compile Workflow
    app = workflow.compile()
    
    return app

# Initialize the workflow graph when imported
document_generator_app = create_document_generator_workflow()
