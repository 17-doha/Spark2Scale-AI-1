import logging
from .state import DocumentGeneratorState
from .swot.scraper import scrape_competitor_reviews, analyze_weaknesses
from .swot.regulatory_and_barrier_node import scrape_regulatory_barriers
from .swot.gap_analyzer import analyze_competitive_gap
from .swot.data_extractor import extract_swot_data
from .swot.synthesizer import synthesize_swot_matrix
from .swot.generator import generate_swot_document

logger = logging.getLogger("DocumentGeneratorNodes")

def scrape_competitors_node(state: DocumentGeneratorState) -> dict:
    logger.info("--- Node: scrape_competitors_node ---")
    reviews = scrape_competitor_reviews(state["idea_name"], state["market_research"])
    if not reviews:
        return {"errors": ["scrape_competitors_node failed to return reviews."]}
    return {"reviews_data": reviews}

def analyze_gaps_node(state: DocumentGeneratorState) -> dict:
    logger.info("--- Node: analyze_gaps_node ---")
    gap_data = analyze_competitive_gap(state["idea_name"], state.get("reviews_data", {}), state.get("idea_description", ""))
    if not gap_data:
        return {"errors": ["analyze_gaps_node failed to return gap data."]}
    return {"gap_data": gap_data}

def scrape_barriers_node(state: DocumentGeneratorState) -> dict:
    logger.info("--- Node: scrape_barriers_node ---")
    barriers = scrape_regulatory_barriers(state["idea_name"], state.get("region", "Global"))
    if not barriers:
         return {"errors": ["scrape_barriers_node failed to return barrier data."]}
    return {"barriers_data": barriers}

def analyze_weaknesses_node(state: DocumentGeneratorState) -> dict:
    logger.info("--- Node: analyze_weaknesses_node ---")
    weaknesses = analyze_weaknesses(state["idea_name"], state["market_research"], state.get("idea_description", ""), state.get("region", "Global"))
    if not weaknesses:
         return {"errors": ["analyze_weaknesses_node failed to return weakness data."]}
    return {"weaknesses_data": weaknesses}

def assemble_swot_context_node(state: DocumentGeneratorState) -> dict:
    logger.info("--- Node: assemble_swot_context_node ---")
    swot_context = extract_swot_data(
        idea_name=state["idea_name"],
        market_research=state["market_research"],
        weaknesses_data=state.get("weaknesses_data", {}),
        reviews_data=state.get("reviews_data", {}),
        gap_data=state.get("gap_data", {}),
        barrier_data=state.get("barriers_data", {}),
        tows_data=None # Not yet generated
    )
    if swot_context and "error" in swot_context:
        return {"errors": [swot_context["error"]]}
    return {"swot_context": swot_context}

def synthesize_tows_node(state: DocumentGeneratorState) -> dict:
    logger.info("--- Node: synthesize_tows_node ---")
    tows_data = synthesize_swot_matrix(state["idea_name"], state.get("swot_context", {}))
    if not tows_data:
         return {"errors": ["synthesize_tows_node failed to return TOWS data."]}
         
    # Update the swot_context to include the TOWS data for the final generation
    updated_swot_context = extract_swot_data(
        idea_name=state["idea_name"],
        market_research=state["market_research"],
        weaknesses_data=state.get("weaknesses_data", {}),
        reviews_data=state.get("reviews_data", {}),
        gap_data=state.get("gap_data", {}),
        barrier_data=state.get("barriers_data", {}),
        tows_data=tows_data
    )     
    return {"tows_data": tows_data, "swot_context": updated_swot_context}

def generate_swot_node(state: DocumentGeneratorState) -> dict:
    logger.info("--- Node: generate_swot_node ---")
    swot_document = generate_swot_document(state["idea_name"], state.get("swot_context", {}))
    if swot_document and "error" in swot_document:
        return {"errors": [swot_document["error"]]}
    return {"swot_document": swot_document}
