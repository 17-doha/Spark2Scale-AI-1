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


def _as_text(payload: Any) -> str:
    """Return trimmed free-text if the payload arrived as a prose string, else ''."""
    return payload.strip() if isinstance(payload, str) and payload.strip() else ""


def _available_evidence(ctx: Dict[str, Any]) -> List[str]:
    """The source labels the model is actually allowed to cite — only the blocks
    that genuinely hold data. Used both to instruct the LLM and to enforce
    citation integrity downstream (see node._enforce_integrity)."""
    raw = ctx.get("raw_text_inputs") or {}
    avail: List[str] = []

    mr_keys = ("executive_summary", "opportunity_analysis", "market_sizing",
               "competitors", "validation", "trends")
    if any(ctx.get(k) for k in mr_keys) or raw.get("market_research"):
        avail.append("Market Research")
    if ctx.get("competitors"):
        avail.append("Competitors")
    if ctx.get("market_sizing"):
        avail.append("Market Sizing")
    if ctx.get("opportunity_analysis"):
        avail.append("Opportunity Analysis")
    if ctx.get("validation"):
        avail.append("Validation")
    if ctx.get("trends"):
        avail.append("Trends")
    if ctx.get("finance") or ctx.get("startup_costs") or ctx.get("monthly_fixed_costs"):
        avail += ["Finance", "Pricing", "Startup Costs", "Monthly Fixed Costs"]

    ev = ctx.get("evaluation") or {}
    if (isinstance(ev, dict) and any(v for v in ev.values())) or raw.get("evaluation"):
        avail.append("Evaluation")

    rec = ctx.get("recommendation") or {}
    if (isinstance(rec, dict) and any(v for v in rec.values())) or raw.get("recommendation"):
        avail.append("Recommendation")
        if rec.get("customer_quotes"):
            avail.append("Customer Quotes")

    return avail


def _first(*vals: Any) -> Any:
    """Return the first value that isn't None/empty."""
    for v in vals:
        if v not in (None, "", [], {}):
            return v
    return None


def _slim_evaluation(evaluation: Dict[str, Any]) -> Dict[str, Any]:
    """Pull the BMC-relevant slices from the evaluation report.

    Tolerates two shapes: the evaluation-agent's nested
    `final_report.founder_output.Content.*`, and a flat shape where
    verdict/scorecard/etc. sit at the top level (common in hand-built payloads).
    """
    if not isinstance(evaluation, dict) or not evaluation:
        return {}

    # The two consumer-facing summaries live under final_report (agent shape).
    final = evaluation.get("final_report") or {}
    founder = (final.get("founder_output") or {}).get("Content") or {}
    investor = (final.get("investor_output") or {}).get("Content") or {}
    rationales = investor.get("Dimension Rationales") or []

    def _explanation(dim: str) -> Any:
        report = evaluation.get(f"{dim}_report")
        return report.get("explanation") if isinstance(report, dict) else None

    return {
        # Nested agent shape first, then flat top-level fallback.
        "verdict": _first(founder.get("Verdict"), investor.get("Verdict"), evaluation.get("verdict")),
        "weighted_score": _first(founder.get("Weighted Score"), investor.get("Weighted Score"), evaluation.get("weighted_score")),
        "scorecard": _first(founder.get("Scorecard Grid"), investor.get("Scorecard Grid"), evaluation.get("scorecard")),
        "executive_summary": _first(founder.get("Executive Summary"), investor.get("Executive Summary"), evaluation.get("executive_summary")),
        "top_priorities": _first(founder.get("Top 3 Priorities"), evaluation.get("top_priorities")),
        "deal_breakers": _first(investor.get("Deal Breakers"), evaluation.get("deal_breakers")),
        "dimension_rationales": rationales,
        # Per-dimension explanations — guarded against string/None report blocks.
        "dimension_explanations": {
            dim: _explanation(dim)
            for dim in (
                "team", "problem", "product", "market", "traction",
                "gtm", "business", "vision", "operations",
            )
            if _explanation(dim)
        },
    }


def _slim_recommendation(recommendation: Dict[str, Any]) -> Dict[str, Any]:
    """Pull the BMC-relevant slices from the recommendation-agent output.

    Tolerates two shapes per refined statement: the agent's nested
    {"original","recommended","why_better"} object, and a plain string (common
    in hand-built payloads). Likewise patterns_detected may be dicts or strings.
    """
    if not isinstance(recommendation, dict) or not recommendation:
        return {}

    insights = recommendation.get("insights") or {}
    refined = recommendation.get("refined_statements") or {}
    if not isinstance(refined, dict):
        refined = {}

    # Refined statements are LLM-polished restatements — better BMC source
    # material than raw insights. Accept a dict {recommended:...} OR a plain string.
    def _refined_or_raw(field: str) -> Any:
        block = refined.get(field)
        if isinstance(block, dict):
            val = block.get("recommended") or block.get("original")
            if val:
                return val
        elif isinstance(block, str) and block.strip():
            return block
        # Fall back to raw insights, then any top-level field on the doc.
        return insights.get(field) or recommendation.get(field)

    # patterns_detected may be a list of dicts (agent) or strings (variant).
    top_patterns: List[Dict[str, Any]] = []
    for p in (recommendation.get("patterns_detected") or recommendation.get("top_patterns") or [])[:5]:
        if isinstance(p, dict):
            top_patterns.append({"name": p.get("name"), "template": p.get("template"), "strength": p.get("strength_label")})
        elif isinstance(p, str) and p.strip():
            top_patterns.append({"name": p, "template": p, "strength": None})

    return {
        "stage": recommendation.get("stage"),
        "company_name": insights.get("company_name") or recommendation.get("company_name"),
        "company_context": recommendation.get("company_context"),
        "problem_statement": _refined_or_raw("problem_statement"),
        "differentiation": _refined_or_raw("differentiation"),
        "gap_analysis": _refined_or_raw("gap_analysis"),
        "core_stickiness": _refined_or_raw("core_stickiness"),
        "beachhead_market": _refined_or_raw("beachhead_market"),
        "five_year_vision": _refined_or_raw("five_year_vision"),
        "founder_market_fit": _refined_or_raw("founder_market_fit"),
        "founder_experience": insights.get("founder_experience") or recommendation.get("founder_experience"),
        "customer_quotes": insights.get("customer_quotes") or recommendation.get("customer_quotes"),
        "active_users": insights.get("active_users"),
        "early_revenue": insights.get("early_revenue"),
        "target_raise": insights.get("target_raise") or recommendation.get("target_raise"),
        "evaluation_scores": recommendation.get("evaluation_scores"),
        "top_patterns": top_patterns,
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

    # Preserve any inputs that arrived as free text (not structured JSON) so the
    # prompt can still ground bullets in them instead of fabricating evidence.
    raw_text_inputs = {
        key: txt
        for key, txt in (
            ("market_research", _as_text(market_research)),
            ("evaluation", _as_text(evaluation)),
            ("recommendation", _as_text(recommendation)),
        )
        if txt
    }

    finance = mr.get("finance") if isinstance(mr.get("finance"), dict) else {}
    startup_costs = _get(finance, "startup_costs") or _get(mr, "startup_costs")
    monthly_fixed_costs = _get(finance, "monthly_fixed_costs") or _get(mr, "monthly_fixed_costs")

    competitors: List[Dict[str, Any]] = mr.get("competitors") or []
    if isinstance(competitors, list):
        competitors = competitors[:8]  # cap prompt size

    context = {
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
        # Free-text fallback for any source that wasn't structured JSON.
        "raw_text_inputs": raw_text_inputs,
    }
    # Whitelist of citable sources (only those that actually hold data).
    context["available_evidence"] = _available_evidence(context)
    return context
