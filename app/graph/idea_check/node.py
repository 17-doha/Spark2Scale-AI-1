import json
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from app.core.llm import get_llm
from app.core.logger import get_logger

from app.graph.idea_check.state import IdeaCheckState
from app.graph.idea_check.prompts import generate_validation_queries_prompt, analyze_pain_points_prompt
from app.graph.idea_check.tools import execute_search_queries

logger = get_logger(__name__)


def _safe_parse_json(raw: str) -> dict:
    """
    Strip markdown fences and parse JSON.
    Returns an empty dict on failure so the graph degrades gracefully
    instead of crashing the whole LangGraph run.
    """
    text = raw.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"[Idea Check] JSON parse failed: {e}\nRaw output: {text[:300]}")
        return {}


async def generate_queries_node(state: IdeaCheckState) -> IdeaCheckState:
    logger.info("[Idea Check] Generating validation queries...")
    try:
        llm = get_llm(temperature=0, provider="modal")
        region = state.get("region", "Global")
        prompt_text = generate_validation_queries_prompt(
            state["idea"], state["problem"], region
        )

        # Use StrOutputParser instead of JsonOutputParser so we can apply
        # _safe_parse_json ourselves -- JsonOutputParser has no recovery path
        # if the model emits a markdown fence or any preamble.
        chain = PromptTemplate.from_template("{prompt}") | llm | StrOutputParser()
        raw = await chain.ainvoke({"prompt": prompt_text})
        queries_dict = _safe_parse_json(raw)

        if not queries_dict:
            return {**state, "error": "Query generation returned unparseable JSON."}

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

        if not queries:
            return {**state, "error": "No queries were generated — cannot run search."}

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
        llm = get_llm(temperature=0.2, provider="modal")
        region = state.get("region", "Global")
        prompt_text = analyze_pain_points_prompt(
            state["idea"],
            state["problem"],
            state["search_evidence"],
            region,
        )

        chain = PromptTemplate.from_template("{prompt}") | llm | StrOutputParser()
        raw = await chain.ainvoke({"prompt": prompt_text})
        analysis = _safe_parse_json(raw)

        if not analysis:
            return {**state, "error": "Pain analysis returned unparseable JSON."}

        # Attach the raw queries for debugging / traceability
        analysis["key_queries_executed"] = state.get("validation_queries", {})

        return {**state, "analysis_result": analysis}
    except Exception as e:
        logger.error(f"[Idea Check] analyze_pain_points_node failed: {e}")
        return {**state, "error": f"Pain point analysis failed: {e}"}