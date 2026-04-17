"""
Extracts the slices of the three input JSON files that the BMC prompt references.

Sources:
  - `market_research.json` — full market-research agent output (may be wrapped
    in `{"data": {...}}` from the C# client).
  - `evaluation.json` — full evaluation-agent output (gtm_report, team_report,
    market_report, ..., plus `final_report.founder_output` and `investor_output`).
  - `recommendation.json` — recommendation-agent output (`insights`,
    `evaluation_scores`, `patterns_detected`, `refined_statements`,
    `recommendation_report`).

We tolerate variants where `startup_costs` / `monthly_fixed_costs` are at the
top level of the market-research payload (older exports) and where any payload
is itself wrapped in a `{"data": {...}}` envelope.
"""
from __future__ import annotations
from typing import Any, Dict, List


def _coerce_to_dict(payload: Any) -> Dict[str, Any]:
    """Unwrap common transport wrappers so callers always get a dict."""
    if payload is None:
        return {}
    if isinstance(payload, list):
        payload = payload[0] if payload else {}
    if isinstance(payload, dict):
        if "items" in payload and isinstance(payload["items"], list):
            payload = payload["items"][0] if payload["items"] else {}
        if "data" in payload and isinstance(payload["data"], (dict, list)):
            inner = payload["data"]
            if isinstance(inner, list):
                inner = inner[0] if inner else {}
            if isinstance(inner, dict):
                payload = inner
    return payload if isinstance(payload, dict) else {}


def _get(d: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, "", [], {}):
            return d[k]
    return default


def _slim_evaluation(evaluation: Dict[str, Any]) -> Dict[str, Any]:
    """Pull the BMC-relevant slices from the (large) evaluation report."""
    if not evaluation:
        return {}

    # The two consumer-facing summaries live under final_report.
    final = evaluation.get("final_report") or {}
    founder = (final.get("founder_output") or {}).get("Content") or {}
    investor = (final.get("investor_output") or {}).get("Content") or {}

    # Per-dimension scores + 1-line rationales — useful for value_proposition,
    # customer_segments, key_resources, key_activities.
    rationales = investor.get("Dimension Rationales") or []

    return {
        "verdict": founder.get("Verdict") or investor.get("Verdict"),
        "weighted_score": founder.get("Weighted Score") or investor.get("Weighted Score"),
        "scorecard": founder.get("Scorecard Grid") or investor.get("Scorecard Grid"),
        "executive_summary": founder.get("Executive Summary") or investor.get("Executive Summary"),
        "top_priorities": founder.get("Top 3 Priorities"),
        "deal_breakers": investor.get("Deal Breakers"),
        "dimension_rationales": rationales,
        # Per-dimension explanations from the per-report blocks.
        "dimension_explanations": {
            dim: (evaluation.get(f"{dim}_report") or {}).get("explanation")
            for dim in (
                "team", "problem", "product", "market", "traction",
                "gtm", "business", "vision", "operations",
            )
            if (evaluation.get(f"{dim}_report") or {}).get("explanation")
        },
    }


def _slim_recommendation(recommendation: Dict[str, Any]) -> Dict[str, Any]:
    """Pull the BMC-relevant slices from the recommendation-agent output."""
    if not recommendation:
        return {}

    insights = recommendation.get("insights") or {}
    refined = recommendation.get("refined_statements") or {}

    # Refined statements are LLM-polished restatements — much better source
    # material for BMC bullets than the raw insights when both exist.
    def _refined_or_raw(field: str) -> Any:
        block = refined.get(field) or {}
        return block.get("recommended") or insights.get(field)

    return {
        "stage": recommendation.get("stage"),
        "company_name": insights.get("company_name"),
        "company_context": recommendation.get("company_context"),
        "problem_statement": _refined_or_raw("problem_statement"),
        "differentiation": _refined_or_raw("differentiation"),
        "gap_analysis": _refined_or_raw("gap_analysis"),
        "core_stickiness": _refined_or_raw("core_stickiness"),
        "beachhead_market": _refined_or_raw("beachhead_market"),
        "five_year_vision": _refined_or_raw("five_year_vision"),
        "founder_market_fit": _refined_or_raw("founder_market_fit"),
        "founder_experience": insights.get("founder_experience"),
        "customer_quotes": insights.get("customer_quotes"),
        "active_users": insights.get("active_users"),
        "early_revenue": insights.get("early_revenue"),
        "target_raise": insights.get("target_raise"),
        "evaluation_scores": recommendation.get("evaluation_scores"),
        # Top patterns drive the strategic actions — useful for key_activities.
        "top_patterns": [
            {"name": p.get("name"), "template": p.get("template"), "strength": p.get("strength_label")}
            for p in (recommendation.get("patterns_detected") or [])[:5]
        ],
    }


def extract_bmc_context(
    idea_name: str,
    idea_description: str,
    region: str,
    market_research: Any,
    evaluation: Any = None,
    recommendation: Any = None,
) -> Dict[str, Any]:
    """Build the compact context dict that gets injected into the BMC prompt."""
    mr = _coerce_to_dict(market_research)
    ev = _coerce_to_dict(evaluation)
    rec = _coerce_to_dict(recommendation)

    finance = mr.get("finance") if isinstance(mr.get("finance"), dict) else {}
    startup_costs = _get(finance, "startup_costs") or _get(mr, "startup_costs")
    monthly_fixed_costs = _get(finance, "monthly_fixed_costs") or _get(mr, "monthly_fixed_costs")

    competitors: List[Dict[str, Any]] = mr.get("competitors") or []
    if isinstance(competitors, list):
        competitors = competitors[:8]  # cap prompt size

    return {
        "idea_name": idea_name or mr.get("idea_name"),
        "idea_description": idea_description,
        "region": region or "Global",
        # Market research slices
        "executive_summary": mr.get("executive_summary"),
        "opportunity_analysis": mr.get("opportunity_analysis"),
        "market_sizing": mr.get("market_sizing"),
        "competitors": competitors,
        "validation": mr.get("validation"),
        "finance": finance,
        "startup_costs": startup_costs,
        "monthly_fixed_costs": monthly_fixed_costs,
        "trends": mr.get("trends"),
        # Cross-source slices
        "evaluation": _slim_evaluation(ev),
        "recommendation": _slim_recommendation(rec),
    }
