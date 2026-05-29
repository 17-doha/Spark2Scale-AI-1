import json
import base64
import asyncio
import os
import aiohttp
from datetime import datetime
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from playwright.async_api import async_playwright
from json_repair import repair_json
from app.core.llm import get_llm
from app.core.logger import get_logger
from app.graph.evaluation_agent.prompts.general_prompts import NORMALIZER_PROMPT
try:
    from langchain_community.tools import DuckDuckGoSearchRun
except ImportError:
    DuckDuckGoSearchRun = None

logger = get_logger(__name__)

# T5 client lives in app.core.llm — imported here so other helpers can reach it
from app.core.llm import get_t5_insight, _get_t5_client  # noqa: E402
t5_client = None   # kept as a module-level alias for backward-compat with tests

TARGET_SCHEMA = {
  "startup_evaluation": {
    "meta_data": { "form_type": "Pre-Seed & Seed Evaluation", "last_updated": "2026-03-24" },
    "company_snapshot": {
      "company_name": "",
      "website_url": "",
      "hq_location": "",
      "date_founded": "YYYY-MM-DD",
      "current_stage": "",
      "amount_raised_to_date": 0,  # Changed to number
      "current_round": { 
          "target_amount": 0,      # Changed to number
          "target_close_date": "YYYY-MM-DD" 
      }
    },
    "founder_and_team": {
      "founders": [
        {
          "name": "",
          "role": "",
          "ownership_percentage": 0,
          "prior_experience": "",
          "years_direct_experience": 0,
          "founder_market_fit_statement": ""
        }
      ],
      "execution": { 
          "full_time_start_date": "YYYY-MM-DD", 
          "key_shipments": [{"date": "YYYY-MM-DD", "item": ""}] 
      }
    },
    "problem_definition": {
      "customer_profile": { "role": "", "company_size": "", "industry": "" },
      "problem_statement": "",
      "current_solution": "",
      "gap_analysis": "",
      "frequency": "High/Medium/Low",
      "impact_metrics": { "cost_type": "", "description": "" },
      "evidence": { "interviews_conducted": 0, "customer_quotes": [] }
    },
    "product_and_solution": {
      "product_stage": "Concept / MVP / Live",
      "demo_link": "",
      "core_stickiness": "",
      "differentiation": "",
      "defensibility_moat": ""
    },
    "market_and_scope": {
      "beachhead_market": "",
      "market_size_estimate": "",
      "long_term_vision": "",
      "expansion_strategy": ""
    },
    "traction_metrics": {
      "stage_context": "",
      "user_count": 0,
      "active_users_monthly": 0,
      "partnerships_and_lois": [],
      "early_revenue": 0,          # Changed to number
      "growth_rate": 0             # Changed to number (percentage)
    },
    "gtm_strategy": {
      "buyer_persona": "",
      "user_persona": "",
      "primary_acquisition_channel": "",
      "sales_motion": "",
      "average_sales_cycle": "",
      "deal_closer": ""
    },
    "business_model": {
      "pricing_model": "",
      "average_price_per_customer": 0,
      "gross_margin": 0,
      "monthly_burn": 0,
      "runway_months": 0
    },
    "vision_and_strategy": {
      "five_year_vision": "",
      "category_definition": "",
      "primary_risk": "",
      "use_of_funds": []
    }
  }
}
def load_schema(schema_name: str) -> str:
    """
    Loads a JSON schema from the schema.json file.
    """
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    schema_path = os.path.join(current_dir, "schema.json")
    
    with open(schema_path, "r") as f:
        schemas = json.load(f)
        
    return json.dumps(schemas.get(schema_name, {}), indent=2)

def force_numeric_types(data):
    """Recursively ensures fields that should be numbers are actually numbers."""
    numeric_fields = {
        "amount_raised_to_date", "target_amount", "ownership_percentage", 
        "years_direct_experience", "interviews_conducted", "user_count", 
        "active_users_monthly", "early_revenue", "growth_rate", 
        "average_price_per_customer", "gross_margin", "monthly_burn", "runway_months"
    }
    
    if isinstance(data, dict):
        for key, value in data.items():
            if key in numeric_fields:
                if isinstance(value, str):
                    # Strip non-numeric characters except for decimal points
                    clean_val = "".join(c for c in value if c.isdigit() or c == '.')
                    try:
                        data[key] = float(clean_val) if '.' in clean_val else int(clean_val)
                    except ValueError:
                        data[key] = 0
                elif value is None:
                    data[key] = 0
            else:
                force_numeric_types(value)
    elif isinstance(data, list):
        for item in data:
            force_numeric_types(item)
    return data

def extract_team_data(data):
    """
    Extracts fields for the Founder Market Fit Agent:
    - Founder Profiles (Experience, Role, Ownership)
    - Execution History (Shipments, Start Date)
    - Problem Context (To cross-reference skills vs. the actual problem)
    """
    root = data.get("startup_evaluation", {})
    team_section = root.get("founder_and_team", {})
    problem_section = root.get("problem_definition", {})

    return {
        # --- 1. THE FOUNDERS (Who are they?) ---
        "founders": [
            {
                "name": f.get("name"),
                "role": f.get("role"),
                "equity": f.get("ownership_percentage"),
                "prior_experience": f.get("prior_experience"),
                "years_experience": f.get("years_direct_experience"),
                "fit_statement": f.get("founder_market_fit_statement")
            }
            for f in team_section.get("founders", [])
        ],

        # --- 2. EXECUTION (Can they build?) ---
        "execution_history": {
            "start_date": team_section.get("execution", {}).get("full_time_start_date"),
            "shipments": team_section.get("execution", {}).get("key_shipments", [])
        },

        # --- 3. PROBLEM CONTEXT (Do their skills match this problem?) ---
        # The agent needs to know the problem to judge if the founder is an "Insider"
        "problem_context": {
            "statement": problem_section.get("problem_statement"),
            "current_solution": problem_section.get("current_solution"),
            "gap": problem_section.get("gap_analysis")
        }
    }

def extract_problem_data(data):
    """
    Extracts only the fields necessary for the Problem Evaluation Agent:
    - Clarity & Urgency (Problem Statement, Impact, Frequency)
    - Market Maturity (Current Solutions, Gap, Evidence)
    - Audience Scope (Customer Profile, Beachhead)
    - Founder Alignment (Why them?)
    """
    # Navigate to the main sections safely
    root = data.get("startup_evaluation", {})
    problem_def = root.get("problem_definition", {})
    market_scope = root.get("market_and_scope", {})
    founder_section = root.get("founder_and_team", {})

    return {
        # --- 1. CORE PROBLEM (Clarity & Urgency) ---
        "problem_core": {
            "statement": problem_def.get("problem_statement"),
            "impact": problem_def.get("impact_metrics"), # Includes cost_type & description
            "frequency": problem_def.get("frequency")
        },

        # --- 2. MARKET MATURITY (Why Now?) ---
        "market_maturity": {
            "current_solutions": problem_def.get("current_solution"),
            "gap_analysis": problem_def.get("gap_analysis"),
            "customer_evidence": problem_def.get("evidence", {}).get("customer_quotes", [])
        },

        # --- 3. AUDIENCE (Targeted vs. Broad) ---
        "audience": {
            "profile": problem_def.get("customer_profile"), # Role, Industry, etc.
            "beachhead": market_scope.get("beachhead_market")
        },

        # --- 4. FOUNDER ALIGNMENT (The "Insider" Signal) ---
        # We extract just the fit statement list to save context window
        "founder_alignment_statements": [
            f.get("founder_market_fit_statement", "Not specified") 
            for f in founder_section.get("founders", [])
        ]
    }

def extract_product_data(data):
    root = data.get("startup_evaluation", data)
    snap = root.get("company_snapshot", {})
    prod = root.get("product_and_solution", {})
    prob = root.get("problem_definition", {})
    team = root.get("founder_and_team", {})
    market = root.get("market_and_scope", {})
    vision = root.get("vision_and_strategy", {})

    return {
        "snapshot": {
            "company_name": snap.get("company_name"),
            "website": snap.get("website_url") or snap.get("website"),
            "hq_location": snap.get("hq_location"),
            "date_founded": snap.get("date_founded"),
            "current_stage": snap.get("current_stage"),
            "amount_raised": snap.get("amount_raised_to_date") or snap.get("amount_raised"),
            "current_round": snap.get("current_round")
        },
        "product": {
            "status": prod.get("product_stage") or prod.get("product_status"),
            "demo_link": prod.get("demo_link"),
            "stickiness": prod.get("core_stickiness") or prod.get("stickiness"),
            "differentiation": prod.get("differentiation"),
            "moat": prod.get("defensibility_moat") or prod.get("moat")
        },
        "baseline_solution": prob.get("current_solution") or prob.get("current_state"),
        "problem_gap": prob.get("gap_analysis") or prob.get("gap"),
        "shipping_history": (
            team.get("execution", {}).get("key_shipments")
            or team.get("team_execution")
        ),
        "expansion_roadmap": market.get("expansion_strategy") or market.get("expansion"),
        "category_strategy": vision.get("category_definition") or vision.get("categorization"),
        "future_vision": vision.get("five_year_vision") or vision.get("future_view")
    }


# ==========================================
# NEW EXTRACTION FUNCTIONS
# ==========================================

def extract_market_data(data):
    """
    Transforms raw startup JSON into the simplified structure needed for Market Analysis.
    """
    root = data.get("startup_evaluation", data)
    snapshot = root.get("company_snapshot", {})
    market = root.get("market_and_scope", {})
    problem = root.get("problem_definition", {})
    business = root.get("business_model", {})
    vision = root.get("vision_and_strategy", {})
    gtm = root.get("gtm_strategy", {})

    return {
        "entry_point": {
            "beachhead_definition": market.get("beachhead_market", "Unknown Market"),
            "target_customer": problem.get("customer_profile", {}),
            "som_size_claim": market.get("market_size_estimate", "Not specified"),
            "location": snapshot.get("hq_location", "Global")
        },
        "scalability": {
            "expansion_plan": market.get("expansion_strategy"),
            "long_term_vision": market.get("long_term_vision"),
            "future_category": vision.get("category_definition")
        },
        "economics": {
            "price": business.get("average_price_per_customer"),
            "pricing_model": business.get("pricing_model"),
            "frequency": problem.get("frequency")
        },
        "risks": {
            "current_competitors": problem.get("current_solution"),
            "stated_risk": vision.get("primary_risk"),
            "acquisition_channel": gtm.get("primary_acquisition_channel")
        }
    }

def extract_traction_data(data):
    """
    Extracts traction metrics tailored strictly to the company's stage (Pre-Seed vs. Seed).
    """
    root = data.get("startup_evaluation", data)
    snapshot = root.get("company_snapshot", {})
    problem = root.get("problem_definition", {})
    evidence = problem.get("evidence", {})
    
    # 1. Determine Stage
    stage_raw = snapshot.get("current_stage", "Pre-Seed").lower()
    
    # 2. Base Context
    base_context = {
        "stage": snapshot.get("current_stage"),
        "founded_date": snapshot.get("date_founded"),
        "current_date": datetime.now().strftime("%Y-%m-%d"),
        "execution_velocity": root.get("founder_and_team", {}).get("execution", {}).get("key_shipments", [])
    }
    
    # 3. Source Sections
    traction = root.get("traction_metrics", {})
    gtm = root.get("gtm_strategy", {})
    biz = root.get("business_model", {})

    # Helper: Determine B2B vs B2C
    industry = problem.get("customer_profile", {}).get("industry", "").lower()
    role = problem.get("customer_profile", {}).get("role", "").lower()
    is_b2b = "business" in industry or "b2b" in industry or "enterprise" in role
    focus_type = "B2B" if is_b2b else "B2C"

    # PATH A: PRE-SEED TRACTION
    if "pre" in stage_raw:
        return {
            "analysis_type": "Pre-Seed Validation",
            "context": base_context,
            "validation_signals": {
                "users_total": traction.get("user_count", 0),
                "users_active": traction.get("active_users_monthly", 0),
                "partnerships_lois": traction.get("partnerships_and_lois", []), 
                "early_revenue": traction.get("early_revenue", "0"),
                "interviews_conducted": evidence.get("interviews_conducted", 0),
                "waitlist_status": "Implied from user count" if traction.get("user_count", 0) > 0 else "None",
                "focus": focus_type,
                "sales_cycle": gtm.get("average_sales_cycle", "Unknown")
            },
            "defensibility": root.get("product_and_solution", {}).get("defensibility_moat", "None")
        }

    # PATH B: SEED TRACTION
    else:
        # Determine if this is a B2C consumer app (pre-revenue is expected/normal)
        active_users = traction.get("active_users_monthly") or traction.get("user_count", 0)
        user_growth = traction.get("revenue_growth_rate") or traction.get("growth_rate")
        is_consumer = not is_b2b
        is_pre_revenue = not traction.get("early_revenue") and not traction.get("monthly_recurring_revenue")
        consumer_note = (
            "IMPORTANT: This is a B2C consumer platform with pre-revenue at Seed stage. "
            "For consumer apps, user growth rate and MAU are the primary traction signals — "
            "NOT MRR. Do NOT apply the 'Fake Seed' rule. Evaluate growth_rate_mom and "
            "active_users as the core traction proof."
            if (is_consumer and is_pre_revenue and active_users and user_growth)
            else None
        )
        return {
            "analysis_type": "Seed Growth",
            "context": {**base_context, **({"consumer_note": consumer_note} if consumer_note else {})},
            "growth_metrics": {
                "mrr": traction.get("early_revenue") or traction.get("monthly_recurring_revenue"),
                "growth_rate_mom": traction.get("revenue_growth_rate") or traction.get("growth_rate", "Not specified"),
                "retention_metrics": traction.get("retention_metrics", "Not specified"),
                "paid_users": traction.get("paying_customer_count") or traction.get("number_of_paying_customers", 0),
                "active_users": traction.get("active_users_monthly") or traction.get("user_count", 0),
                "unit_economics": {
                    "acv": biz.get("average_price_per_customer"),
                    "cac_hint": "Infer from marketing spend if available"
                }
            },
            "sales_machine": {
                "closer": gtm.get("deal_closer"),
                "channel": gtm.get("primary_acquisition_channel") or gtm.get("primary_channel"),
                "sales_cycle": gtm.get("average_sales_cycle"),
                "sales_motion": gtm.get("sales_motion"),
                "conversion_friction": "Low" if gtm.get("sales_motion") == "Self-serve" else "High"
            }
        }

def extract_gtm_pre_seed(data):
    root = data.get("startup_evaluation", data)
    gtm = root.get("gtm_strategy", {})
    problem = root.get("problem_definition", {})
    biz = root.get("business_model", {})
    traction = root.get("traction_metrics", {})
    
    return {
        "analysis_type": "Pre-Seed GTM (Validation)",
        "context": {
            "company_name": root.get("company_snapshot", {}).get("company_name"),
            "founded_date": root.get("company_snapshot", {}).get("date_founded"),
            "stage": "Pre-Seed"
        },
        "target_audience": {
            "icp_description": problem.get("customer_profile", {}), 
            "buyer_persona": gtm.get("buyer_persona"),
            "user_persona": gtm.get("user_persona")
        },
        "early_distribution": {
            "primary_channel": gtm.get("primary_acquisition_channel"),
            "sales_motion": gtm.get("sales_motion"),
            "early_revenue": traction.get("early_revenue", "0")
        },
        "pricing_hypothesis": {
            "price_point": biz.get("average_price_per_customer"),
            "model": biz.get("pricing_model")
        },
        "unit_economics": {
            "burn_rate": biz.get("monthly_burn", 0),
            "total_users": traction.get("active_users_monthly") or traction.get("user_count", 0),
            "paid_users": traction.get("paying_customer_count") or traction.get("number_of_paying_customers", 0),
            "revenue": traction.get("early_revenue", 0),
            "price_point": biz.get("average_price_per_customer", 0)
        }
    }

def extract_gtm_seed(data):
    root = data.get("startup_evaluation", data)
    gtm = root.get("gtm_strategy", {})
    biz = root.get("business_model", {})
    traction = root.get("traction_metrics", {})
    problem = root.get("problem_definition", {})
    
    return {
        "analysis_type": "Seed GTM (Scalability & Economics)",
        "context": {
            "company_name": root.get("company_snapshot", {}).get("company_name"),
            "stage": "Seed"
        },
        "strategy": {
            "icp_description": problem.get("customer_profile", {}),
            "personas": {
                "buyer": gtm.get("buyer_persona"),
                "user": gtm.get("user_persona")
            },
             "pricing_model": biz.get("pricing_model")
        },
        "sales_machine": {
            "primary_channel": gtm.get("primary_acquisition_channel"),
            "closer": gtm.get("deal_closer"),
            "sales_cycle": gtm.get("average_sales_cycle"),
            "sales_motion": gtm.get("sales_motion")
        },
        "unit_economics": {
            "burn_rate": biz.get("monthly_burn"),
            "total_users": traction.get("active_users_monthly") or traction.get("user_count"),
            "paid_users": traction.get("paying_customer_count") or traction.get("number_of_paying_customers", 0),
            "revenue": traction.get("early_revenue") or traction.get("monthly_recurring_revenue"),
            "price_point": biz.get("average_price_per_customer"),
            "gross_margin": biz.get("gross_margin"),
            "growth_rate": traction.get("revenue_growth_rate") or traction.get("growth_rate"),
            "retention": traction.get("retention_metrics")
        }
    }

def extract_business_pre_seed(data):
    root = data.get("startup_evaluation", data)
    biz = root.get("business_model", {})
    traction = root.get("traction_metrics", {})
    funds = root.get("fundraising_and_use_of_funds", {})
    
    problem = root.get("problem_definition", {})
    customer_profile = problem.get("customer_profile", {})
    industry = customer_profile.get("industry", "Unknown Sector")
    role = customer_profile.get("role", "Unknown Buyer")
    sector_info = f"{industry} (Targeting: {role})"

    return {
        "analysis_type": "Pre-Seed Economics (Hypothesis)",
        "sector_context": sector_info,
        "context": {
            "stage": "Pre-Seed",
            "company_name": root.get("company_snapshot", {}).get("company_name")
        },
        "monetization_structure": {
            "pricing_model": biz.get("pricing_model"),
            "price_point": biz.get("average_price_per_customer"),
            "gross_margin": biz.get("gross_margin")
        },
        "early_signals": {
            "revenue": traction.get("early_revenue", "0"),
            "pilots": traction.get("partnerships_and_lois", [])
        },
        "cash_health": {
            "burn_rate": biz.get("monthly_burn"),
            "runway_months": biz.get("runway_months"),
            "capital_ask": funds.get("current_round_target"),
            "spend_plan": funds.get("use_of_funds_over_next_18_months")
        }
    }

def extract_business_seed(data):
    root = data.get("startup_evaluation", data)
    biz = root.get("business_model", {})
    traction = root.get("traction_metrics", {})
    funds = root.get("fundraising_and_use_of_funds", {})
    
    problem = root.get("problem_definition", {})
    customer_profile = problem.get("customer_profile", {})
    industry = customer_profile.get("industry", "Unknown Sector")
    role = customer_profile.get("role", "Unknown Buyer")
    sector_info = f"{industry} (Targeting: {role})"
    
    raw_mrr = traction.get("monthly_recurring_revenue")
    
    if not raw_mrr or raw_mrr == "0":
        try:
            users = float(traction.get("number_of_paying_customers") or 0)
            price = float(biz.get("average_price_per_customer") or 0)
            mrr_value = users * price
        except:
            mrr_value = 0
    else:
        mrr_value = raw_mrr

    return {
        "analysis_type": "Seed Economics (Unit Metrics)",
        "sector_context": sector_info,
        "context": {
            "stage": "Seed",
            "company_name": root.get("company_snapshot", {}).get("company_name")
        },
        "monetization_structure": {
            "pricing_model": biz.get("pricing_model"),
            "price_point": biz.get("average_price_per_customer"),
            "gross_margin": biz.get("gross_margin")
        },
        "cash_health": {
            "burn_rate": biz.get("monthly_burn"),
            "runway_months": biz.get("runway_months"),
            "capital_ask": funds.get("current_round_target"),
            "spend_plan": funds.get("use_of_funds_over_next_18_months")
        },
        "revenue_momentum": {
            "mrr": mrr_value,
            "is_mrr_calculated": (not raw_mrr or raw_mrr=="0"),
            "growth_rate": traction.get("revenue_growth_rate") or traction.get("growth_rate", "0%"),
            "active_users": traction.get("active_users_monthly") or traction.get("user_count", 0),
            "paying_customers": traction.get("number_of_paying_customers") or traction.get("paying_customer_count", 0),
        },
        "retention_health": {
            "churn_metric": traction.get("retention_metrics"), 
            "sales_motion": root.get("gtm_strategy", {}).get("sales_motion") 
        }
    }

def extract_vision_data(data):
    root = data.get("startup_evaluation", data)
    market = root.get("market_and_scope", {})
    product = root.get("product_and_solution", {})
    strategy = root.get("vision_and_strategy", {})
    problem = root.get("problem_definition", {})

    return {
        "analysis_type": "Vision & Narrative Check",
        "context": {
            "stage": root.get("company_snapshot", {}).get("current_stage", "Pre-Seed"),
            "company_name": root.get("company_snapshot", {}).get("company_name")
        },
        "north_star": {
            "5_year_vision": strategy.get("five_year_vision"),
            "long_term_market": market.get("long_term_market_vision") or market.get("long_term_vision"),
            "expansion_plan": market.get("expansion_strategy"),
        },
        "category_play": {
            "definition": strategy.get("category_definition"),
            "differentiation": product.get("differentiation"),
            "moat": product.get("defensibility_moat")
        },
        "customer_obsession": {
            "problem_statement": problem.get("problem_statement"),
            "customer_quotes": problem.get("evidence", {}).get("customer_quotes", [])
        },
        "risk_awareness": {
            "primary_risk": strategy.get("primary_risk")
        }
    }

def extract_operations_data(data):
    root = data.get("startup_evaluation", data)
    snapshot = root.get("company_snapshot", {})
    founders = root.get("founder_and_team", {}).get("founders", [])
    economics = root.get("business_model", {})
    # Support both old "fundraising_and_use_of_funds" key and newer layout
    # where use_of_funds lives inside vision_and_strategy
    fundraising = root.get("fundraising_and_use_of_funds") or {}
    vision_strategy = root.get("vision_and_strategy", {})

    total_founder_equity = sum([float(f.get("ownership_percentage", 0) or 0) for f in founders])
    raw_industry = root.get("problem_definition", {}).get("customer_profile", {}).get("industry", "Technology")
    sector = raw_industry.split("/")[0].strip() if "/" in raw_industry else raw_industry
    
    return {
        "analysis_type": "Operational Readiness Check",
        "context": {
            "stage": snapshot.get("current_stage", "Pre-Seed"),
            "location": snapshot.get("hq_location", "Global"),
            "sector": sector,
            "round_target": snapshot.get("current_round", {}).get("target_amount"),
            "target_close": snapshot.get("current_round", {}).get("target_close_date")
        },
        "cap_table": {
            "total_founder_equity": total_founder_equity,
            "founder_count": len(founders),
            "existing_investors": fundraising.get("existing_investors", "None")
        },
        "financial_health": {
            "monthly_burn": economics.get("monthly_burn"),
            "runway_months": economics.get("runway_months"),
            "gross_margin": economics.get("gross_margin")
        },
        "the_plan": {
            "use_of_funds": (
                fundraising.get("use_of_funds")
                or vision_strategy.get("use_of_funds")
                or fundraising.get("use_of_funds_over_next_18_months")
                or []
            ),
            "milestones": (
                fundraising.get("key_milestones")
                or fundraising.get("milestones")
                or ""
            )
        }
    }
def check_missing_fields(data, parent_path=""):
    '''Recursively checks for empty values in a nested JSON object to identify incomplete data.
    
    Params:
        data - The dictionary or list to be scanned for missing values.
        parent_path - A string tracking the nested key hierarchy for error reporting (defaults to empty string).
        
    Returns:
        list - A list of strings, each detailing the path of a missing or empty field.
    '''
    missing_errors = []

    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{parent_path}.{key}" if parent_path else key

            if value is None or value == "" or value == [] or value == {}:
                missing_errors.append(f"Missing Value: Field '{current_path}' is empty.")
            else:
                missing_errors.extend(check_missing_fields(value, current_path))

    elif isinstance(data, list):
        for index, item in enumerate(data):
            item_path = f"{parent_path}[{index}]"
            missing_errors.extend(check_missing_fields(item, item_path))

    return missing_errors

# async def capture_screenshot(url: str):
#     """
#     Visits a URL using Playwright (Async) and returns the screenshot as a Base64 string.
#     """
#     logger.info(f"📸 Visiting {url} for visual check (Async)...")
    
#     if not url:
#         return {"error": "No URL provided."}

#     try:
#         async with async_playwright() as p:
#             browser = await p.chromium.launch(headless=True)
#             # Create a context with a known viewport and user agent to mimic a real user
#             context = await browser.new_context(
#                 viewport={'width': 1280, 'height': 720},
#                 user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
#             )
#             page = await context.new_page()
            
#             try:
#                 # Wait up to 15 seconds for load
#                 await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                
#                 # Small delay to ensure any JS rendering stabilizes
#                 await asyncio.sleep(3)
                
#                 screenshot_bytes = await page.screenshot(type='png')
#                 image_data = base64.b64encode(screenshot_bytes).decode("utf-8")
                
#                 return {"image_b64": image_data, "status": "Success"}
                
#             except Exception as e:
#                 return {"error": f"Timeout/Access Error: {str(e)}"}
#             finally:
#                 await browser.close()
            
#     except Exception as e:
#         return {"error": f"Playwright Driver Error: {str(e)}"}
    

# ==========================================
# SEARCH HELPER FUNCTIONS (ASYNC OPTIMIZED)
# ==========================================

def generate_queries(vision_data: dict) -> tuple[str, list]:
    """Helper to generate queries for Vision Analysis."""
    current_year = datetime.now().year
    forecast_year = current_year + 5
    category = vision_data.get("category_play", {}).get("definition", "")
    search_topic = category if len(category) > 3 else "startup market trends"
    
    queries = [
        f"future of {search_topic} market {forecast_year} forecast",
        f"VC investment trends in {search_topic} {current_year}",
        f"is {search_topic} market growing or shrinking {current_year}?",
        f"risks and regulation for {search_topic} startups {current_year}"
    ]
    return search_topic, queries

async def get_market_signals_serper(vision_data: dict) -> str:
    """Runs search using Google Serper API via Async HTTP (Parallelized)."""
    logger.info("[GLOBAL] Running Market Search (Serper/Google)...")
    
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key: return "No Serper API Key found."

    _, queries = generate_queries(vision_data)
    raw_results = []
    url = "https://google.serper.dev/search"
    headers = {
        'X-API-KEY': api_key,
        'Content-Type': 'application/json'
    }
    
    # --- HELPER FOR SINGLE REQUEST ---
    async def fetch_query(session, q):
        try:
            async with session.post(url, headers=headers, json={"q": q}) as response:
                if response.status == 200:
                    data = await response.json()
                    organic = data.get('organic', [])[:2] 
                    return [f"SOURCE: {q}\nTitle: {r.get('title')}\nSnippet: {r.get('snippet')}" for r in organic]
        except Exception as e:
            logger.error(f"Serper error for query '{q}': {e}")
        return []

    # --- EXECUTE IN PARALLEL ---
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_query(session, q) for q in queries]
        results_list = await asyncio.gather(*tasks)
        
        # Flatten results
        for res in results_list:
            raw_results.extend(res)

    return "\n".join(raw_results) if raw_results else "No Serper results found."

def get_market_signals_duckduckgo(vision_data: dict) -> str:
    """Runs search using DuckDuckGo (Synchronous Fallback)."""
    if DuckDuckGoSearchRun is None: return "DuckDuckGo tool not installed."
    logger.info("   -> Running DuckDuckGo Search (Fallback)...")
    _, queries = generate_queries(vision_data)
    raw_results = []
    try:
        ddg = DuckDuckGoSearchRun()
        raw_results.append(f"SOURCE (DuckDuckGo): {ddg.run(queries[0])[:300]}...") 
        return "\n".join(raw_results)
    except Exception as e:
        return f"DuckDuckGo Error: {str(e)}"
    
def parse_and_repair_json(raw_text: str) -> dict:
    """
    Robustly parses JSON from LLM output, handling Markdown and unescaped quotes.
    """
    try:
        # 1. Strip Markdown code blocks if present
        cleaned_text = raw_text.replace("```json", "").replace("```", "").strip()
        
        # 2. Use json_repair to handle broken syntax (quotes, commas, etc.)
        parsed = json.loads(repair_json(cleaned_text))
        return parsed
    except Exception as e:
        logger.error(f"[ERROR] JSON Repair Failed: {e} | Raw: {raw_text[:100]}...")
        # Return safe fallback to prevent pipeline crash
        return {
            "score": "0/5", 
            "explanation": "Error parsing model output.",
            "score_numeric": 0,
            "red_flags": ["Model Output Error"],
            "green_flags": []
        }

def safe_score_numeric(result_dict: dict) -> int:
    """Extracts numeric score 0-100 from string 'X/5'."""
    try:
        score_str = str(result_dict.get('score', "0")).split("/")[0]
        # Remove any non-numeric chars
        import re
        clean_score = re.search(r"(\d+(\.\d+)?)", score_str)
        if clean_score:
            val = float(clean_score.group(1))
            return int(val * 20) # Convert 0-5 to 0-100
        return 0
    except:
        return 0


async def normalize_input_data(raw_input: str) -> dict:
    """
    Takes any string input (messy text, partial JSON) and returns the strict Schema JSON.
    """
    # ── Fast path: input is already valid structured JSON ─────────────────────
    # When the frontend submits a properly-formed payload (or a PDF extraction
    # is passed directly), running it through Modal/Gemma3n would corrupt numeric
    # fields — Gemma maps them to the schema's default zeros.
    # Skip the LLM entirely if the payload already has the top-level wrapper.
    try:
        candidate = json.loads(raw_input) if isinstance(raw_input, str) else raw_input
        if isinstance(candidate, dict) and "startup_evaluation" in candidate:
            logger.info("🧹 Input already structured — skipping LLM normalization.")
            force_numeric_types(candidate)
            return candidate
        # Inner dict without wrapper — wrap it and skip
        if isinstance(candidate, dict) and any(
            k in candidate for k in ("company_snapshot", "founder_and_team", "traction_metrics")
        ):
            logger.info("🧹 Input already structured (unwrapped) — skipping LLM normalization.")
            wrapped = {"startup_evaluation": candidate}
            force_numeric_types(wrapped)
            return wrapped
    except (json.JSONDecodeError, TypeError):
        pass

    # ── Slow path: free-text or schema-mismatched input → LLM normalization ───
    logger.info("🧹 Normalizing Input Data via LLM...")
    llm = get_llm(temperature=0, provider="modal")
    chain = PromptTemplate.from_template(NORMALIZER_PROMPT) | llm | JsonOutputParser()

    try:
        normalized_json = await chain.ainvoke({
            "target_schema": json.dumps(TARGET_SCHEMA, indent=2),
            "raw_input": raw_input
        })

        if "startup_evaluation" not in normalized_json:
            return {"startup_evaluation": normalized_json}

        return normalized_json

    except Exception as e:
        logger.error(f"Normalization Failed: {e}")
        return TARGET_SCHEMA


# ---------------------------------------------------------------------------
# T5-3B ASYNC WRAPPER  — delegates to app.core.llm.get_t5_insight
# ---------------------------------------------------------------------------

async def fetch_t5_deep_insight(user_data: dict) -> str:
    """
    Convenience wrapper used by t5_insight_node.
    Builds a plain-text prompt from the startup state dict, then calls
    the canonical get_t5_insight() from app.core.llm.
    """
    snapshot = user_data.get("startup_evaluation", {}).get("company_snapshot", {})
    problem  = user_data.get("startup_evaluation", {}).get("problem_definition", {})

    prompt = (
        f"Evaluate the following startup context: "
        f"Company: {snapshot.get('company_name', 'Unknown')}, "
        f"Stage: {snapshot.get('current_stage', 'Unknown')}. "
        f"Problem: {problem.get('problem_statement', 'Not provided')}"
    )
    logger.info("🧠 Sending prompt to T5-3B model via Gradio...")
    result = await get_t5_insight(prompt)
    logger.info("🧠 T5-3B response received.")
    return result