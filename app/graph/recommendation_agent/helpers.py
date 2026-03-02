import json

def calculate_trigger_strength(severity, multipliers, cross_category_support=False):
    base_weight = 0.7
    strength = round(base_weight * multipliers.get(severity, 1.0), 2)
    if cross_category_support:
        strength = round(strength * 1.2, 2)
    return strength

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

    return {
        "company_name": snap.get("company_name", "Unknown"),
        "stage": snap.get("current_stage", "Unknown"),
        "target_raise": snap.get("current_round", {}).get("target_amount", "Unknown"),
        "problem_statement": prob.get("problem_statement", "Unknown"),
        "founder_experience": found.get("founders", [{}])[0].get("prior_experience", "Unknown"),
        "founder_market_fit": found.get("founders", [{}])[0].get("founder_market_fit_statement", "Unknown"),
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