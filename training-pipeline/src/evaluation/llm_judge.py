"""
src/evaluation/llm_judge.py
────────────────────────────
Gemini-based LLM-as-a-judge evaluator for QA model outputs.
Returns structured JSON scores: Coherence, Consistency, Conciseness,
Structure, Hallucination Freedom, plus a final decision.
"""

import json
import random
import time
from typing import Any, Dict

import google.generativeai as genai

from src.utils import get_logger

logger = get_logger(__name__)


class GeminiJudge:
    """Wraps the Gemini API for structured QA evaluation."""

    def __init__(self, model_name: str, api_key: str):
        self.model_name = model_name
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        logger.info(f"GeminiJudge initialised with {model_name}")

    # ── Internal API call with retry ─────────────────────────────────────────

    def _call_api(self, prompt: str, retries: int = 5) -> Dict[str, Any]:
        response_schema = {
            "type": "object",
            "properties": {
                "score": {"type": "integer"},
                "final_decision": {"type": "string"},
                "executive_summary": {"type": "string"},
                "dimension_scores": {
                    "type": "object",
                    "properties": {
                        "Coherence": {"type": "integer"},
                        "Consistency": {"type": "integer"},
                        "Conciseness": {"type": "integer"},
                        "Structure": {"type": "integer"},
                        "Hallucination_Freedom": {"type": "integer"},
                    },
                },
                "hallucination_report": {
                    "type": "object",
                    "properties": {
                        "risk_level": {"type": "string"},
                        "flagged_claims": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "critical_analysis": {
                    "type": "object",
                    "properties": {
                        "strengths": {"type": "array", "items": {"type": "string"}},
                        "weaknesses": {"type": "array", "items": {"type": "string"}},
                        "logic_gaps": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
        }

        for attempt in range(retries):
            try:
                response = self.model.generate_content(
                    prompt,
                    generation_config={
                        "response_mime_type": "application/json",
                        "response_schema": response_schema,
                    },
                )
                return json.loads(response.text)
            except Exception as exc:
                err = str(exc)
                if "503" in err or "429" in err:
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"API busy – retrying in {wait:.1f}s …")
                    time.sleep(wait)
                else:
                    return {"error": f"API Error: {err}"}

        return {"error": "Failed after max retries"}

    # ── Public evaluate method ────────────────────────────────────────────────

    def evaluate(self, question: str, context: str, generated_response: str) -> Dict[str, Any]:
        MAX_CTX = 3000
        ctx = context[:MAX_CTX] + ("\n\n[CONTEXT TRUNCATED...]" if len(context) > MAX_CTX else "")

        qa_block = (
            f"QUESTION: {json.dumps(question)}\n"
            f"CONTEXT: {json.dumps(ctx)}\n"
            f"GENERATED ANSWER: {json.dumps(generated_response)}"
        )

        prompt = f"""
Act as an independent, expert QA Auditor. Rigorously evaluate the Generated Answer
using the Question and Context provided.

### INPUT DATA:
{qa_block}

### EVALUATION DIMENSIONS:
1. Core Quality: Factuality, Completeness, Relevance
2. Writing Quality: Coherence (1-5), Consistency (1-5), Conciseness (1-5)
3. Risk Assessment: Hallucination Freedom (1-5, 5=no hallucinations), Structure (1-5)

### DECISION LOGIC:
- Score >= 7 AND Hallucination_Freedom >= 4 → APPROVED
- Otherwise → REJECTED

Return ONLY the JSON object described in the schema.
""".strip()

        return self._call_api(prompt)
