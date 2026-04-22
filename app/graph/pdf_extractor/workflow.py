from langgraph.graph import StateGraph, START, END
from app.graph.pdf_extractor.state import PDFExtractorState
from app.graph.pdf_extractor.node import extract_text_node, llm_extraction_node, sanitize_data_node

# Define Graph
builder = StateGraph(PDFExtractorState)

# Add Nodes
builder.add_node("extract_text", extract_text_node)
builder.add_node("llm_extraction", llm_extraction_node)
builder.add_node("sanitize_data", sanitize_data_node)

# Add Edges
builder.add_edge(START, "extract_text")
builder.add_edge("extract_text", "llm_extraction")
builder.add_edge("llm_extraction", "sanitize_data")
builder.add_edge("sanitize_data", END)

# Compile Graph
pdf_extractor_app = builder.compile()
