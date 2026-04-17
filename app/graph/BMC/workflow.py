from langgraph.graph import StateGraph, START, END

from app.core.logger import get_logger
from .node import extract_context_node, generate_bmc_node
from .state import BMCState

logger = get_logger("BMCWorkflow")


def create_bmc_workflow():
    workflow = StateGraph(BMCState)

    workflow.add_node("extract_context", extract_context_node)
    workflow.add_node("generate_bmc", generate_bmc_node)

    workflow.add_edge(START, "extract_context")
    workflow.add_edge("extract_context", "generate_bmc")
    workflow.add_edge("generate_bmc", END)

    return workflow.compile()


bmc_app = create_bmc_workflow()
