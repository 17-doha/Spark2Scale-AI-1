import json
import os
import time
from google import genai
from .state import RecommendationState
from app.core.config import Config
from app.utils.logger import logger
from .prompts import SYSTEM_ADVISOR_PROMPT, RECOMMENDATION_PROMPT_TEMPLATE, STATEMENT_IMPROVEMENT_PROMPT

def recommendation_node(state: RecommendationState):
    """
    Generates strategic recommendations based on evaluation results.
    """
    try:
        # Get API key from config
        api_key = Config.GEMINI_API_KEY
        if not api_key:
            logger.error("GEMINI_API_KEY not configured. Please set it in your .env file.")
            return {"recommendation": "Error: GEMINI_API_KEY not configured. Please set it in your .env file."}
        
        # Extract evaluation output - it might be a string (JSON) or already a dict
        eval_output = state.get("evaluation")
        if isinstance(eval_output, str):
            try:
                eval_output = json.loads(eval_output)
            except json.JSONDecodeError:
                # If it's not valid JSON, try to construct a basic structure
                # This is a fallback - ideally evaluation should output proper JSON
                logger.error(f"Could not parse evaluation output. Received: {eval_output[:100]}...")
                return {"recommendation": f"Error: Could not parse evaluation output. Received: {eval_output[:100]}..."}
        
        # Extract raw input - this should be the original input data
        # It might be in input_idea or we need to construct it from state
        raw_input = state.get("input_idea")
        
        # If input_idea is a string, try to parse it as JSON
        if isinstance(raw_input, str):
            try:
                raw_input = json.loads(raw_input)
            except json.JSONDecodeError:
                # If it's not JSON, construct a basic structure
                # This assumes the evaluation already processed the raw data
                # We'll use a minimal structure that extract_key_insights can handle
                raw_input = {
                    "startup_evaluation": {
                        "company_snapshot": {"company_name": "Unknown"},
                        "problem_definition": {"problem_statement": raw_input, "evidence": {"customer_quotes": []}},
                        "founder_and_team": {"founders": [{}]},
                        "product_and_solution": {"differentiation": "Unknown"},
                        "traction_metrics": {}
                    }
                }
        
        # If raw_input is still None or not a dict, create a minimal structure
        if not isinstance(raw_input, dict):
            raw_input = {
                "startup_evaluation": {
                    "company_snapshot": {"company_name": "Unknown"},
                    "problem_definition": {"problem_statement": str(raw_input), "evidence": {"customer_quotes": []}},
                    "founder_and_team": {"founders": [{}]},
                    "product_and_solution": {"differentiation": "Unknown"},
                    "traction_metrics": {}
                }
            }
        
        # Run the recommendation agent (import here to avoid circular import)
        from .workflow import run_recommendation_agent
        result = run_recommendation_agent(raw_input, eval_output, api_key, save_output=True)
        
        # Handle the return value - it now returns a dict with all results
        if isinstance(result, dict):
            return {
                "recommendation": result.get("final_report"),
                "recommendation_files": result.get("output_paths"),
                "insights": result.get("insights"),
                "matched_patterns": result.get("matched_patterns"),
                "refined_statements": result.get("refined_statements"),
                "market_signals": result.get("market_signals")
            }
        
        # Backward compatibility for tuple
        elif isinstance(result, tuple):
            final_report, output_paths = result
            return {
                "recommendation": final_report,
                "recommendation_files": output_paths
            }
        else:
            # Backward compatibility if save_output was False
            return {"recommendation": result}
    
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error in recommendation_node: {error_details}")
        return {"recommendation": f"Error in recommendation agent: {str(e)}"}


class AgentNodes:
    def __init__(self, api_key):
        # self.client = genai.Client(api_key="AIzaSyBvX80EbeRGsstF2RqUmyk4z0iBCrjQn-k")
        self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        self.model_id = "gemini-3-flash-preview"

    def improve_statements(self, insights, max_retries=3, retry_delay=2):
        statements = {
            "problem_statement": insights.get('problem_statement', 'N/A'),
            "founder_market_fit": insights.get('founder_market_fit', 'N/A'),
            "differentiation": insights.get('differentiation', 'N/A'),
            "core_stickiness": insights.get('core_stickiness', 'N/A'),
            "five_year_vision": insights.get('five_year_vision', 'N/A'),
            "beachhead_market": insights.get('beachhead_market', 'N/A'),
            "gap_analysis": insights.get('gap_analysis', 'N/A')
        }
        
        prompt = STATEMENT_IMPROVEMENT_PROMPT.format(
            statements_json=json.dumps(statements, indent=2),
            quotes_json=json.dumps(insights.get('customer_quotes', []), indent=2)
        )
        
        for attempt in range(max_retries):
            try:
                # Add temperature config from environment
                api_config = {'temperature': Config.GEMINI_TEMPERATURE}
                response = self.client.models.generate_content(
                    model=self.model_id, 
                    contents=prompt,
                    config=api_config
                )
                # Handle cleaning of potential markdown
                text = response.text.strip().replace("```json", "").replace("```", "")
                return json.loads(text)
            except Exception as e:
                error_msg = str(e)
                
                # Handle 503/overload errors with retry
                if "503" in error_msg or "overloaded" in error_msg.lower() or "unavailable" in error_msg.lower():
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (attempt + 1)
                        print(f"[WARNING] API temporarily unavailable (503). Retrying in {wait_time} seconds... (Attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise ValueError(
                            "[ERROR] API Service Error: Gemini API is currently overloaded (503).\n"
                            "This is a temporary issue on Google's side.\n"
                            "Please try again in a few minutes."
                        ) from e
                elif "429" in error_msg or "resource_exhausted" in error_msg.lower():
                     logger.warning("API Quota Exceeded (429) for refined statements. Skipping refinement step.")
                     return None
                elif "suspended" in error_msg.lower() or "403" in error_msg:
                    raise ValueError(
                        "[ERROR] API Key Error: Your Gemini API key has been suspended or is invalid.\n"
                        "Please:\n"
                        "1. Get a new API key from: https://aistudio.google.com/apikey\n"
                        "2. Update your .env file with: GEMINI_API_KEY=your_new_key\n"
                        "3. Make sure the API key has access to Gemini API"
                    ) from e
                elif "401" in error_msg or "unauthorized" in error_msg.lower():
                    raise ValueError(
                        "[ERROR] API Key Error: Invalid or unauthorized API key.\n"
                        "Please check your GEMINI_API_KEY in the .env file."
                    ) from e
                else:
                    # Log the specific error to a file for debugging
                    with open("debug_error.log", "a") as f:
                        f.write(f"API Error in improve_statements: {str(e)}\n")
                    raise

    def synthesize_report(self, data, patterns, insights, replacements, market_signals, max_retries=3, retry_delay=2):
        # Format market intelligence strings
        country_risk_json = json.dumps(market_signals.get('country_risk', {}), indent=2) if market_signals else "{}"
        news_signals_json = json.dumps(market_signals.get('news_signals', []), indent=2) if market_signals else "[]"
        risk_flags_json = json.dumps(market_signals.get('risk_flags', []), indent=2) if market_signals else "[]"
        intel_confidence = market_signals.get('confidence', 'unknown') if market_signals else "unknown"

        prompt = RECOMMENDATION_PROMPT_TEMPLATE.format(
            company_name=insights['company_name'],
            stage=data.stage,
            company_context=data.company_context,
            scores_json=data.scores.model_dump_json(indent=2),
            patterns_json=json.dumps(patterns, indent=2),
            problem_statement=insights['problem_statement'],
            quotes_json=json.dumps(insights['customer_quotes']),
            target_raise=insights['target_raise'],
            replacements_json=json.dumps(replacements),
            country_risk_json=country_risk_json,
            news_signals_json=news_signals_json,
            risk_flags_json=risk_flags_json,
            intel_confidence=intel_confidence
        )
        
        for attempt in range(max_retries):
            try:
                # Add temperature config along with system instruction
                api_config = {
                    'system_instruction': SYSTEM_ADVISOR_PROMPT,
                    'temperature': Config.GEMINI_TEMPERATURE
                }
                response = self.client.models.generate_content(
                    model=self.model_id,
                    config=api_config,
                    contents=prompt
                )
                return response.text
            except Exception as e:
                error_msg = str(e)
                
                # Handle 503/overload errors with retry
                if "503" in error_msg or "overloaded" in error_msg.lower() or "unavailable" in error_msg.lower():
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (attempt + 1)
                        print(f"[WARNING] API temporarily unavailable (503). Retrying in {wait_time} seconds... (Attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise ValueError(
                            "[ERROR] API Service Error: Gemini API is currently overloaded (503).\n"
                            "This is a temporary issue on Google's side.\n"
                            "Please try again in a few minutes."
                        ) from e
                elif "429" in error_msg or "resource_exhausted" in error_msg.lower():
                     raise ValueError(
                         "[ERROR] API Quota Exceeded (429). You have reached the free tier limit for Gemini API.\n"
                         "Please check your usage at: https://aistudio.google.com/app/plan_information"
                     ) from e
                elif "suspended" in error_msg.lower() or "403" in error_msg:
                    raise ValueError(
                        "[ERROR] API Key Error: Your Gemini API key has been suspended or is invalid.\n"
                        "Please:\n"
                        "1. Get a new API key from: https://aistudio.google.com/apikey\n"
                        "2. Update your .env file with: GEMINI_API_KEY=your_new_key\n"
                        "3. Make sure the API key has access to Gemini API"
                    ) from e
                elif "401" in error_msg or "unauthorized" in error_msg.lower():
                    raise ValueError(
                        "[ERROR] API Key Error: Invalid or unauthorized API key.\n"
                        "Please check your GEMINI_API_KEY in the .env file."
                    ) from e
                else:
                    # Log the specific error to a file for debugging
                    with open("debug_error.log", "a") as f:
                        f.write(f"API Error in synthesize_report: {str(e)}\n")
                    raise