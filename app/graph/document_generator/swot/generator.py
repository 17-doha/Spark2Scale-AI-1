import os
import logging
from app.core.llm import get_llm
from .data_extractor import extract_swot_data
from app.graph.document_generator.prompts import swot_prompt_template

logger = logging.getLogger("SWOTGenerator")

def generate_swot_document(idea_name: str, provider: str = "gemini") -> str:
    """
    Generates a full SWOT Markdown document for a given idea name.
    
    Args:
        idea_name (str): The name of the business idea to generate for.
        provider (str): LLM provider to use (default: gemini).
        
    Returns:
        str: The generated Markdown content, or an error message.
    """
    logger.info(f"Generating SWOT analysis for: {idea_name}")
    
    # 1. Extract context data
    context = extract_swot_data(idea_name)
    if "error" in context:
        logger.error(context["error"])
        return context["error"]
        
    # Format context for the prompt
    def format_list(items):
        return "\n".join([f"- {item}" for item in items]) if items else "No specific data found."
        
    strengths_str = format_list(context["strengths_context"])
    weaknesses_str = format_list(context["weaknesses_context"])
    opportunities_str = format_list(context["opportunities_context"])
    threats_str = format_list(context["threats_context"])
    
    # 2. Extract TOWS
    tows_str = "\n\n".join(context.get("tows_strategies", [])) if context.get("tows_strategies") else "TOWS Strategies pending."
    verdict_str = context.get("strategic_verdict", "Verdict pending.")
    
    # 3. Get LLM instance
    try:
        llm = get_llm(temperature=0.7, provider=provider)
    except Exception as e:
        logger.error(f"Failed to initialize LLM: {e}")
        return f"Error initializing LLM: {str(e)}"
        
    # 3. Create chain and invoke
    try:
        chain = swot_prompt_template | llm
        
        logger.info("Invoking LLM for SWOT Generation...")
        response = chain.invoke({
            "idea_name": context["idea_name"],
            "executive_summary": context["executive_summary"][:1000] + "..." if len(context["executive_summary"]) > 1000 else context["executive_summary"],
            "strengths_context": strengths_str,
            "weaknesses_context": weaknesses_str,
            "opportunities_context": opportunities_str,
            "threats_context": threats_str,
            "tows_strategies": tows_str,
            "strategic_verdict": verdict_str
        })
        
        markdown_content = response.content
        
        # 4. Save to file
        output_dir = "data_output"
        os.makedirs(output_dir, exist_ok=True)
        
        # Use clean name for filename
        clean_name = idea_name.replace(' ', '_').replace('"', '').replace("'", "")
        output_file = f"{output_dir}/{clean_name}_SWOT_Analysis.md"
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(markdown_content)
            
        logger.info(f"SWOT Analysis generated successfully: {output_file}")
        return markdown_content
        
    except Exception as e:
        logger.error(f"Failed during SWOT LLM generation: {e}")
        return f"Error generating SWOT document: {str(e)}"
