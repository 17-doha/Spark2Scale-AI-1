import json
import os
import time
from .state import RecommendationState
from app.core.config import Config
from app.core.llm import get_llm
from app.utils.logger import logger
from .prompts import SYSTEM_ADVISOR_PROMPT, RECOMMENDATION_PROMPT_TEMPLATE, STATEMENT_IMPROVEMENT_PROMPT

# Report generation runs through app.core.llm.get_llm. Defaults to Gemini
# (Config.GEMINI_MODEL). Env-overridable — set RECOMMENDATION_LLM_PROVIDER=groq
# or =ollama (+ RECOMMENDATION_LLM_MODEL) to switch providers. The news payload
# is trimmed to keep the prompt within smaller context windows.
RECOMMENDATION_LLM_PROVIDER = os.environ.get("RECOMMENDATION_LLM_PROVIDER", "gemini")
RECOMMENDATION_LLM_MODEL = os.environ.get("RECOMMENDATION_LLM_MODEL", Config.GEMINI_MODEL)
_MAX_NEWS_ITEMS = 6
_MAX_SNIPPET_CHARS = 280
_RATE_LIMIT_MARKERS = ("rate limit", "rate_limit", "429", "quota", "resource_exhausted", "too many requests")


def _strip_code_fences(text: str) -> str:
    return (text or "").strip().replace("```json", "").replace("```", "").strip()


def _trim_news_signals(news_signals):
    """Shrink the scraped news payload so the full report prompt fits an 8K context."""
    trimmed = []
    for n in (news_signals or [])[:_MAX_NEWS_ITEMS]:
        trimmed.append({
            "title": n.get("title", ""),
            "source_domain": n.get("source_domain", ""),
            "url": n.get("url", ""),
            "snippet": (n.get("snippet") or "")[:_MAX_SNIPPET_CHARS],
        })
    return trimmed

def recommendation_node(state: RecommendationState):
    """
    Generates strategic recommendations based on evaluation results.
    """
    try:
        # Report generation now runs on Groq (see AgentNodes); the Gemini key is
        # no longer required. Kept only for backward-compatible call signatures.
        api_key = Config.GEMINI_API_KEY

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
    def __init__(self, api_key=None):
        # api_key is accepted for backward-compatible call signatures but unused:
        # generation runs on Groq, which sources keys via the round-robin rotator
        # in app.core.llm. Provider/model are env-overridable.
        self.provider = RECOMMENDATION_LLM_PROVIDER
        self.model_id = RECOMMENDATION_LLM_MODEL
        self.temperature = Config.GEMINI_TEMPERATURE

    def _llm(self, json_mode=True):
        return get_llm(temperature=self.temperature, provider=self.provider, model_name=self.model_id, json_mode=json_mode)

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
                # JSON mode on: refinements must come back as structured JSON.
                response = self._llm(json_mode=True).invoke(prompt)
                text = _strip_code_fences(response.content)
                return json.loads(text)
            except json.JSONDecodeError:
                # Model returned non-JSON. Don't crash the run — return None so the
                # workflow's passthrough fallback still renders Statement Refinements.
                logger.warning("Refined statements: model returned non-JSON; using passthrough fallback.")
                return None
            except Exception as e:
                error_msg = str(e).lower()
                if any(marker in error_msg for marker in _RATE_LIMIT_MARKERS):
                    logger.warning("Refined statements: Groq rate/quota limit hit. Skipping refinement step.")
                    return None
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                logger.error(f"improve_statements failed permanently: {e}")
                raise

    def synthesize_report(self, data, patterns, insights, replacements, market_signals, max_retries=3, retry_delay=2):
        # Format market intelligence strings
        tool_status = market_signals.get('tool_status', {}) if market_signals else {}
        country_risk = market_signals.get('country_risk', {}) if market_signals else {}
        news_signals = market_signals.get('news_signals', []) if market_signals else []

        # Safety catch: if a tool was offline/timed out (ran but returned nothing),
        # hand the LLM an explicit {"status": "Tool offline"} marker so it adjusts
        # its tone instead of falsely concluding no market data or competitors exist.
        if not country_risk and tool_status.get('world_bank') == 'offline':
            country_risk_json = json.dumps({"status": "Tool offline"}, indent=2)
        else:
            country_risk_json = json.dumps(country_risk, indent=2)

        if not news_signals and tool_status.get('tavily') == 'offline':
            news_signals_json = json.dumps({"status": "Tool offline"}, indent=2)
        else:
            # Trim so the prompt stays small enough for compact local models.
            news_signals_json = json.dumps(_trim_news_signals(news_signals), indent=2)

        risk_flags_json = json.dumps(market_signals.get('risk_flags', []), indent=2) if market_signals else "[]"
        intel_confidence = market_signals.get('confidence', 'unknown') if market_signals else "unknown"

        prompt = RECOMMENDATION_PROMPT_TEMPLATE.format(
            company_name=insights.get('company_name', 'Unknown'),
            stage=data.stage,
            company_context=data.company_context,
            scores_json=data.scores.model_dump_json(indent=2),
            patterns_json=json.dumps(patterns, indent=2),
            problem_statement=insights.get('problem_statement', 'Unknown'),
            quotes_json=json.dumps(insights.get('customer_quotes', [])),
            target_raise=insights.get('target_raise', 'Unknown'),
            replacements_json=json.dumps(replacements),
            country_risk_json=country_risk_json,
            news_signals_json=news_signals_json,
            risk_flags_json=risk_flags_json,
            intel_confidence=intel_confidence
        )

        # System instruction + user prompt as a chat message pair (Groq/LangChain).
        messages = [("system", SYSTEM_ADVISOR_PROMPT), ("human", prompt)]

        for attempt in range(max_retries):
            try:
                # JSON mode off: the report is free-text markdown, not JSON.
                response = self._llm(json_mode=False).invoke(messages)
                return response.content
            except Exception as e:
                error_msg = str(e).lower()
                is_rate_limited = any(marker in error_msg for marker in _RATE_LIMIT_MARKERS)
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                if is_rate_limited:
                    raise ValueError(
                        "[ERROR] LLM rate limit / quota exceeded for report synthesis. "
                        "Please retry in a moment (or switch RECOMMENDATION_LLM_PROVIDER)."
                    ) from e
                logger.error(f"synthesize_report failed permanently: {e}")
                raise