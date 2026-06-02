import json

from app.utils.logger import logger


def _normalize_evaluation_payload(payload):
    """
    Coerce a stored evaluation document's ``json_response`` into the shape
    ``extract_key_insights`` expects: a dict with a top-level
    ``"startup_evaluation"`` key.

    The ``documents`` table stores ``json_response`` either as a JSON string
    or an already-parsed dict, and either wrapped (``{"startup_evaluation": …}``)
    or unwrapped (the inner object directly). This flattens all four cases.
    Returns ``None`` when the payload can't be turned into a usable dict.
    """
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            return None

    if not isinstance(payload, dict):
        return None

    if "startup_evaluation" in payload:
        return payload

    # Unwrapped evaluation object — wrap it so the path lookups line up.
    if any(k in payload for k in ("company_snapshot", "problem_definition",
                                  "founder_and_team", "product_and_solution")):
        return {"startup_evaluation": payload}

    return None


def fetch_startup_evaluation_from_db(startup_id):
    """
    Load the full, enriched startup evaluation for ``startup_id`` from Supabase.

    Mirrors how the other documents source their company context
    (see ``app/graph/pitch_analyzer/main.py``): it reads the ``documents``
    table and returns the evaluation document's ``json_response`` — the
    complete ``startup_evaluation`` object with every field the founder
    submitted (differentiation, gap_analysis, founder_market_fit, vision,
    beachhead, etc.). The ``/recommend`` payload's ``raw_input`` is often a
    partial early submission, which is why those fields rendered as "None".

    Defensive by design: any failure (no client, no row, bad JSON) returns
    ``None`` so the caller transparently falls back to the passed ``raw_input``.
    """
    if not startup_id:
        return None

    try:
        from app.core.supabase_client import supabase
    except Exception as e:  # import-time failure shouldn't break the run
        logger.warning(f"Supabase client unavailable for evaluation fetch: {e}")
        return None

    if supabase is None:
        logger.warning("Supabase client not initialized; cannot fetch startup evaluation.")
        return None

    try:
        result = (
            supabase.table("documents")
            .select("type, json_response")
            .eq("startup_id", startup_id)
            .execute()
        )
    except Exception as e:
        logger.error(f"Failed to fetch evaluation document for startup_id={startup_id}: {e}")
        return None

    rows = result.data or []
    for row in rows:
        doc_type = (row.get("type") or "").lower()
        # Match the same evaluation-doc heuristic the pitch analyzer uses.
        if "evaluation" in doc_type:
            normalized = _normalize_evaluation_payload(row.get("json_response"))
            if normalized:
                logger.info(
                    f"Loaded startup evaluation from DB for startup_id={startup_id} "
                    f"(document type='{row.get('type')}')."
                )
                return normalized

    logger.warning(
        f"No usable evaluation document found in DB for startup_id={startup_id}; "
        "falling back to the raw_input supplied in the request."
    )
    return None


# Funding-stage maturity index. A weakness that is forgivable early becomes a
# kill signal once a startup claims a later stage.
STAGE_ORDER = {
    "idea": 0, "pre-seed": 0, "preseed": 0, "pre seed": 0,
    "seed": 1,
    "series a": 2, "series-a": 2, "a": 2,
    "series b": 3, "series-b": 3, "b": 3,
    "series c": 4, "series-c": 4, "c": 4, "growth": 4, "late": 4,
}

# Maturity index at/after which a weakness in this pillar is mission-critical.
# Example: GTM is a minor warning pre-seed but a kill signal by Series A.
# Keys MUST match the category token in a pattern id (FP-<TOKEN>-NNN), e.g. "ECON".
CATEGORY_CRITICAL_STAGE = {
    "TEAM": 0, "PROBLEM": 0, "PRODUCT": 1, "MARKET": 1,
    "TRACTION": 2, "GTM": 2, "ECON": 2, "OPS": 2, "VISION": 3,
}


def stage_amplifier(stage, category):
    """
    Scale a risk signal by how unacceptable a weakness in this pillar is at the
    startup's current stage, graded by how far past (or before) its criticality
    onset the startup is.

    Returns 1.0 (no change) when stage or category is unknown — preserving the
    original deterministic strength for callers that don't pass them.

    `distance = stage_index - criticality_onset`:
      - >= +2 -> 2.0  long overdue (should have been solid stages ago)
      -   +1  -> 1.9  overdue
      -    0  -> 1.8  just became mission-critical (a Series-A GTM gap, etc.)
      -   -1  -> 1.0  normal warning, one stage early
      -   -2  -> 0.7  premature concern
      - <= -3 -> 0.5  far too early to matter
    The graded escalation lets a fundamental gap (e.g. Team at Series A) outrank a
    pillar that has only just become critical, instead of flattening everything to 1.8.
    """
    if not stage or not category:
        return 1.0
    s_idx = STAGE_ORDER.get(str(stage).lower().strip(), 1)
    onset = CATEGORY_CRITICAL_STAGE.get(str(category).upper(), 1)
    distance = s_idx - onset
    if distance >= 2:
        return 2.0
    elif distance == 1:
        return 1.9
    elif distance == 0:
        return 1.8
    elif distance == -1:
        return 1.0
    elif distance == -2:
        return 0.7
    return 0.5


def calculate_trigger_strength(severity, multipliers, cross_category_support=False, stage=None, category=None):
    base_weight = 0.7
    strength = base_weight * multipliers.get(severity, 1.0)
    if cross_category_support:
        strength *= 1.2
    strength *= stage_amplifier(stage, category)
    return round(strength, 2)

def extract_key_insights(raw_data):
    ev = raw_data.get("startup_evaluation", {})
    snap = ev.get("company_snapshot", {})
    prob = ev.get("problem_definition", {})
    found = ev.get("founder_and_team", {})
    prod = ev.get("product_and_solution", {})
    trac = ev.get("traction_metrics", {})
    
    # Attempt to extract country and sector
    country = snap.get("location", snap.get("country", ""))
    if not country:
        # Fallback to checking the snapshot text broadly
        country_str = str(snap).lower()
        for potential in ["egypt", "tunisia", "uae", "saudi arabia", "jordan", "morocco"]:
            if potential in country_str:
                country = potential
                break
                
    sector = snap.get("industry", snap.get("sector", ""))
    if not sector:
        # Infer from problem definition or solution
        combined_text = (str(prob) + " " + str(prod)).lower()
        if "fintech" in combined_text or "finance" in combined_text or "payment" in combined_text:
            sector = "fintech"
        elif "health" in combined_text or "medical" in combined_text:
            sector = "healthtech"
        elif "ed" in combined_text and "tech" in combined_text or "education" in combined_text:
            sector = "edtech"
        elif "e-commerce" in combined_text or "ecommerce" in combined_text:
            sector = "e-commerce"
        else:
             sector = "technology"

    # Resolve the primary (first) founder safely. The previous
    # `found.get("founders", [{}])[0]` pattern crashed with IndexError
    # when "founders" was present but an empty list (e.g., founders=[]).
    # The default `[{}]` only kicks in when the key is missing, not when
    # the value is empty. Use `or [{}]` so any falsy value also falls back.
    first_founder = (found.get("founders") or [{}])[0]

    return {
        "company_name": snap.get("company_name", "Unknown"),
        "stage": snap.get("current_stage", "Unknown"),
        "target_raise": snap.get("current_round", {}).get("target_amount", "Unknown"),
        "problem_statement": prob.get("problem_statement", "Unknown"),
        "founder_experience": first_founder.get("prior_experience", "Unknown"),
        "founder_market_fit": first_founder.get("founder_market_fit_statement", "Unknown"),
        "customer_quotes": prob.get("evidence", {}).get("customer_quotes", []),
        "differentiation": prod.get("differentiation", "Unknown"),
        "core_stickiness": prod.get("core_stickiness", "Unknown"),
        "active_users": trac.get("active_users_monthly", 0),
        "early_revenue": trac.get("early_revenue", "USD 0"),
        "five_year_vision": ev.get("vision_and_strategy", {}).get("five_year_vision", "Unknown"),
        "beachhead_market": ev.get("market_and_scope", {}).get("beachhead_market", "Unknown"),
        "gap_analysis": prob.get("gap_analysis", "Unknown"),
        "country": country,
        "sector": sector
    }