import os
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.llm import get_llm
from app.core.logger import get_logger
from .state import PPTGenerationState
from .schema import PPTDraft, Critique
from .prompts import GENERATOR_SYSTEM_PROMPT, RECOMMENDER_SYSTEM_PROMPT, REFINER_SYSTEM_PROMPT, IMPROVER_SYSTEM_PROMPT

logger = get_logger(__name__)
llm = get_llm(temperature=0, provider="gemini") 

def generator_node(state: PPTGenerationState) -> PPTGenerationState:
    logger.info(f"--- GENERATING PPT DRAFT (Mode: {state.get('mode', 'create')}) ---")
    research_content = state["research_data"]
    
    structured_llm = llm.with_structured_output(PPTDraft)
    
    mode = state.get("mode", "create")
    system_prompt = IMPROVER_SYSTEM_PROMPT if mode == "edit" else GENERATOR_SYSTEM_PROMPT
    
    if mode == "edit":
        human_msg = f"Improve this existing presentation to match elite pitch standards while keeping its original sequence:\n\n{research_content}"
    else:
        human_msg = f"Create a premium pitch presentation from this research:\n\n{research_content}"

    response: PPTDraft = structured_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_msg),
    ])
    
    # Preserve customization fields
    response.logo_path = state.get("logo_path")
    response.color_palette = state.get("color_palette")
    response.use_default_colors = state.get("use_default_colors", True)
    
    return {"draft": response, "iteration": state["iteration"]}

def recommender_node(state: PPTGenerationState) -> PPTGenerationState:
    logger.info("--- RECOMMENDING IMPROVEMENTS ---")
    draft = state["draft"]
    structured_llm = llm.with_structured_output(Critique)
    
    response = structured_llm.invoke([
        SystemMessage(content=RECOMMENDER_SYSTEM_PROMPT),
        HumanMessage(content=f"Review this presentation draft:\n\n{draft.model_dump_json()}")
    ])
    
    return {"critique": response, "iteration": state["iteration"]}

def refiner_node(state: PPTGenerationState) -> PPTGenerationState:
    logger.info("--- REFINING PPT DRAFT ---")
    draft = state["draft"]
    critique = state["critique"]
    research_content = state["research_data"]
    
    structured_llm = llm.with_structured_output(PPTDraft)
    
    response: PPTDraft = structured_llm.invoke([
        SystemMessage(content=REFINER_SYSTEM_PROMPT),
        HumanMessage(content=f"Refine this draft based on the critique.\n\nDraft: {draft.model_dump_json()}\n\nCritique: {critique.model_dump_json()}")
    ])
    
    response.logo_path = state.get("logo_path")
    response.color_palette = state.get("color_palette")
    response.use_default_colors = state.get("use_default_colors", True)
    
    return {"draft": response, "iteration": state["iteration"] + 1}