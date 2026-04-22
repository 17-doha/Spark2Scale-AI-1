import json
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from app.core.llm import get_llm
from app.core.logger import get_logger

from app.graph.idea_check.state import IdeaCheckState
from app.graph.idea_check.prompts import generate_validation_queries_prompt, analyze_pain_points_prompt
from app.graph.idea_check.tools import execute_search_queries

logger = get_logger(__name__)

async def generate_queries_node(state: IdeaCheckState) -> IdeaCheckState:
    logger.info("[Idea Check] Generating validation queries...")
    try:
        llm = get_llm(temperature=0, provider="gemini")
        prompt_text = generate_validation_queries_prompt(state["idea"], state["problem"])
        chain = PromptTemplate.from_template("{prompt}") | llm | JsonOutputParser()
        
        queries_dict = await chain.ainvoke({"prompt": prompt_text})
        return {**state, "validation_queries": queries_dict}
    except Exception as e:
        logger.error(f"[Idea Check] generate_queries_node failed: {e}")
        return {**state, "error": f"Query generation failed: {e}"}

async def execute_search_node(state: IdeaCheckState) -> IdeaCheckState:
    if state.get("error"):
        return state

    logger.info("[Idea Check] Executing validation searches...")
    try:
        queries = []
        val_queries = state.get("validation_queries", {})
        queries.extend(val_queries.get("problem_queries", []))
        queries.extend(val_queries.get("solution_queries", []))
        
        evidence = await execute_search_queries(queries)
        return {**state, "search_evidence": evidence}
    except Exception as e:
        logger.error(f"[Idea Check] execute_search_node failed: {e}")
        return {**state, "error": f"Search execution failed: {e}"}

async def analyze_pain_points_node(state: IdeaCheckState) -> IdeaCheckState:
    if state.get("error"):
        return state

    logger.info("[Idea Check] Analyzing pain points based on evidence...")
    try:
        llm = get_llm(temperature=0.2, provider="gemini")
        prompt_text = analyze_pain_points_prompt(
            state["idea"], 
            state["problem"], 
            state["search_evidence"]
        )
        chain = PromptTemplate.from_template("{prompt}") | llm | JsonOutputParser()
        
        analysis = await chain.ainvoke({"prompt": prompt_text})
        
        # Attach the raw queries to final output for debugging/traceability
        analysis["key_queries_executed"] = state.get("validation_queries", {})
        
        return {**state, "analysis_result": analysis}
    except Exception as e:
        logger.error(f"[Idea Check] analyze_pain_points_node failed: {e}")
        return {**state, "error": f"Pain point analysis failed: {e}"}
