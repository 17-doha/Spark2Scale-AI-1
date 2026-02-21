"""
Configuration for Market Research Agent - Controls realism and quality thresholds
"""
import re

class ResearchConfig:
    """Central configuration for realistic market research parameters"""
    
    # ========================================
    # SEARCH QUOTA LIMITS (Increase for better accuracy)
    # ========================================
    MAX_COMPETITOR_QUERIES = 5  # Was: 2 (hardcoded)
    MAX_VALIDATION_QUERIES_PER_TYPE = 3  # Was: 1 (hardcoded)
    MAX_FINANCE_QUERIES = 4  # Was: 2 (hardcoded)
    MAX_MARKET_SIZE_QUERIES = 3  # Was: 1 (hardcoded)
    SEARCH_RESULTS_PER_QUERY = 10  # Number of results to fetch per search
    
    # ========================================
    # OPPORTUNITY SCORING (More Conservative)
    # ========================================
    GRADE_A_THRESHOLD = 85  # Raised from 80 - "Gold Mine" should be rare
    GRADE_B_THRESHOLD = 70  # Raised from 60 - "Solid" should be good
    GRADE_C_THRESHOLD = 50  # "Risky" - needs caution
    # Below 50 = Grade D (Not Recommended)
    
    # Scoring Weights (Must sum to 1.0)
    PAIN_WEIGHT = 0.35      # Pain score importance
    GROWTH_WEIGHT = 0.25    # Market growth importance
    MARKET_SIZE_WEIGHT = 0.25  # TAM/SAM importance
    COMPETITION_WEIGHT = 0.15  # Competition level (inverse)
    
    # ========================================
    # EVIDENCE QUALITY THRESHOLDS
    # ========================================
    MIN_VALIDATION_SOURCES = 5  # Minimum evidence pieces for reliable pain score
    MIN_COMPETITOR_SOURCES = 3  # Minimum competitors to analyze
    
    # Evidence quality decay (older = less relevant)
    EVIDENCE_RECENCY_MONTHS = 12  # Only consider posts from last 12 months
    
    # ========================================
    # PAIN SCORE ADJUSTMENTS
    # ========================================
    # Multipliers based on evidence volume
    EVIDENCE_MULTIPLIERS = {
        "minimal": 0.3,    # 1-2 sources found
        "weak": 0.5,       # 3-4 sources found
        "moderate": 0.7,   # 5-7 sources found
        "strong": 0.9,     # 8-10 sources found
        "very_strong": 1.0 # 10+ sources found
    }
    
    # Keywords that indicate high pain (boost score)
    HIGH_PAIN_KEYWORDS = [
        "desperate", "urgent", "broken", "terrible", "awful",
        "waste of time", "frustrated", "hate", "impossible",
        "nightmare", "disaster", "critical", "emergency"
    ]
    
    # Keywords that indicate low pain (reduce score)
    LOW_PAIN_KEYWORDS = [
        "nice to have", "would be cool", "minor", "slight",
        "occasionally", "sometimes", "not a big deal"
    ]
    
    # ========================================
    # FINANCIAL MODEL SETTINGS
    # ========================================
    # Industry Benchmarks for Realistic Estimates
    INDUSTRY_BENCHMARKS = {
        "SaaS": {
            "gross_margin": 0.75,
            "cac_ltv_ratio": 3.0,
            "monthly_churn": 0.05,
            "avg_sales_cycle_days": 30,
            "typical_pricing": "subscription"
        },
        "E-commerce": {
            "gross_margin": 0.40,
            "cac_ltv_ratio": 2.0,
            "monthly_churn": 0.15,
            "avg_sales_cycle_days": 1,
            "typical_pricing": "one-time"
        },
        "Marketplace": {
            "gross_margin": 0.20,
            "cac_ltv_ratio": 4.0,
            "monthly_churn": 0.10,
            "avg_sales_cycle_days": 7,
            "typical_pricing": "commission"
        },
        "Service": {
            "gross_margin": 0.50,
            "cac_ltv_ratio": 2.5,
            "monthly_churn": 0.08,
            "avg_sales_cycle_days": 14,
            "typical_pricing": "hourly/project"
        },
        "Default": {
            "gross_margin": 0.50,
            "cac_ltv_ratio": 2.5,
            "monthly_churn": 0.10,
            "avg_sales_cycle_days": 30,
            "typical_pricing": "varies"
        }
    }
    
    # Conservative startup cost ranges (in USD, adjust by currency)
    STARTUP_COST_RANGES = {
        "minimal": 5000,      # MVP, no-code, solo founder
        "bootstrap": 25000,   # Basic development, small team
        "funded": 100000,     # Professional dev, proper launch
        "well_funded": 500000 # Full product, team, marketing
    }
    
    # ========================================
    # MARKET SIZING VALIDATION
    # ========================================
    # Flags for unrealistic market sizes
    MAX_REASONABLE_TAM_GLOBAL = 10_000_000_000_000  # $10 Trillion (total global economy ~$100T)
    MIN_VIABLE_SOM = 100_000  # $100K - below this, not a real business
    
    # SOM should typically be 1-5% of SAM for startups
    SOM_TO_SAM_RATIO_MIN = 0.001  # 0.1%
    SOM_TO_SAM_RATIO_MAX = 0.05   # 5%
    
    # ========================================
    # VALIDATION SOURCES & WEIGHTS
    # ========================================
    VALIDATION_SOURCES = [
        {"site": "reddit.com", "weight": 0.25, "credibility": "medium"},
        {"site": "twitter.com", "weight": 0.15, "credibility": "low"},
        {"site": "producthunt.com", "weight": 0.20, "credibility": "high"},
        {"site": "trustpilot.com", "weight": 0.15, "credibility": "high"},
        {"site": "g2.com", "weight": 0.15, "credibility": "high"},
        {"site": "ycombinator.com", "weight": 0.10, "credibility": "high"}
    ]
    
    # ========================================
    # COMPETITION ANALYSIS
    # ========================================
    COMPETITION_LEVELS = {
        "Low": {
            "competitor_count": (0, 3),
            "score_multiplier": 1.0,
            "description": "Blue Ocean - Few direct competitors"
        },
        "Medium": {
            "competitor_count": (4, 10),
            "score_multiplier": 0.8,
            "description": "Competitive - Several established players"
        },
        "High": {
            "competitor_count": (11, float('inf')),
            "score_multiplier": 0.6,
            "description": "Red Ocean - Crowded market"
        }
    }
    
    # ========================================
    # TREND ANALYSIS
    # ========================================
    # Growth rate interpretation
    GROWTH_INTERPRETATIONS = {
        "explosive": 100,      # +100% YoY or more
        "high": 50,            # +50% to +100% YoY
        "moderate": 20,        # +20% to +50% YoY
        "slow": 5,             # +5% to +20% YoY
        "flat": 0,             # -5% to +5% YoY
        "declining": -20       # Below -5% YoY
    }
    
    # ========================================
    # QUALITY ASSURANCE FLAGS
    # ========================================
    ENABLE_QUALITY_CHECKS = True  # Enable validation of outputs
    ENABLE_FALLBACK_DATA = True   # Use benchmark data when searches fail
    ENABLE_CONSERVATIVE_MODE = True  # Err on side of caution
    
    # Warning thresholds
    WARN_IF_EVIDENCE_BELOW = 3     # Warn if less than 3 sources
    WARN_IF_SEARCHES_FAIL = True   # Alert if API calls fail
    WARN_IF_SCORES_INCONSISTENT = True  # Alert if pain/growth don't match grade

    RUNWAY_CRITICAL = 3       # Less than 3 months = Imminent death
    RUNWAY_DANGER = 9         # 3 to 9 months = High stress, constant fundraising
    RUNWAY_STANDARD = 18      # 10 to 18 months = Standard seed runway
    
    BREAK_EVEN_EXCELLENT = 12 # 1 year to profitability (Rare)
    BREAK_EVEN_STANDARD = 36  # 3 years to profitability (Normal SaaS)
    BREAK_EVEN_TOXIC = 60     # >5 years (Requires massive VC backing)


# Helper Functions
def get_evidence_quality(evidence_count: int) -> tuple[str, float]:
    """Returns quality level and multiplier based on evidence count"""
    if evidence_count >= 10: return "very_strong", 1.0
    elif evidence_count >= 8: return "strong", 0.9
    elif evidence_count >= 5: return "moderate", 0.7
    elif evidence_count >= 3: return "weak", 0.5
    else: return "minimal", 0.3


def get_competition_level(competitor_count: int) -> dict:
    """Returns competition level analysis"""
    for level, data in ResearchConfig.COMPETITION_LEVELS.items():
        min_count, max_count = data["competitor_count"]
        if min_count <= competitor_count <= max_count:
            return {
                "level": level,
                "multiplier": data["score_multiplier"],
                "description": data["description"],
                "competitor_count": competitor_count
            }
    return ResearchConfig.COMPETITION_LEVELS["High"]  # Default to worst case


def calculate_realistic_opportunity_score(
    pain_score: float,
    growth_pct: float,
    market_size_score: float,
    competitor_count: int,
    evidence_count: int,
    finance_summary: str = ""
) -> dict:
    """
    Calculate opportunity score with realistic VC-style gating for insolvency.
    """
    
    # 1. PAIN & GROWTH SCORING
    evidence_quality, evidence_multiplier = get_evidence_quality(evidence_count)
    if "Low Fit" in finance_summary:
        evidence_multiplier *= 0.5
        
    adjusted_pain_score = pain_score * evidence_multiplier
    
    # Convert growth % to score (0-100 scale)
    if growth_pct < 0:
        growth_score = max(0, 50 - (abs(growth_pct) * 3))
    else:
        growth_score = min(100, 50 + (growth_pct * 1.5))
    
    # 2. COMPETITION SCORING
    competition_data = get_competition_level(competitor_count)
    competition_score = 100 * competition_data["multiplier"]
    
    # 3. FINANCIAL SCORING PARSING
    startup_cost = 0
    monthly_profit = 0
    break_even = 999
    runway = None
    finance_score = 50 # Default
    
    if finance_summary:
        try:
            for line in finance_summary.split('\n'):
                if 'Net Profit' in line:
                    matches = re.findall(r'-?[\d\.]+', line.replace(',',''))
                    if matches: monthly_profit = float(matches[-1])
                elif 'Break-Even Month' in line:
                    matches = re.findall(r'[\d\.]+', line.split()[-1])
                    if matches: break_even = int(float(matches[0]))
                elif 'Runway' in line:
                    matches = re.findall(r'[\d\.]+', line)
                    if matches: runway = float(matches[-1])
        except Exception:
            pass

    # Dynamic Weights (Must sum to 1.0)
    w_pain, w_growth, w_size, w_comp, w_fin = 0.35, 0.20, 0.15, 0.10, 0.20
    
    # Base Weighted Score
    base_score = (
        (adjusted_pain_score * w_pain) +
        (growth_score * w_growth) +
        (market_size_score * w_size) +
        (competition_score * w_comp) +
        (finance_score * w_fin)
    )

    # ==========================================================
    # 4. THE SURVIVAL GATE (CRITICAL FIX)
    # ==========================================================
    survival_multiplier = 1.0
    warnings = []
    
    # Evaluate Runway
    if runway is not None:
        if runway < ResearchConfig.RUNWAY_CRITICAL:
            survival_multiplier = 0.25 # Caps a perfect score at ~25 (Grade D)
            warnings.append(f"🚨 CRITICAL: Imminent insolvency. Runway is only {runway:.1f} months.")
        elif runway < ResearchConfig.RUNWAY_DANGER:
            survival_multiplier = 0.60 # Caps a perfect score at ~60 (Grade C)
            warnings.append(f"⚠️ HIGH RISK: Short runway ({runway:.1f} months). Urgent capital required.")
            
    # Evaluate Path to Profitability
    if break_even >= ResearchConfig.BREAK_EVEN_TOXIC or break_even == 999:
        # If they don't die immediately but have no path to profit
        if survival_multiplier > 0.6: 
            survival_multiplier = 0.70
        warnings.append("⚠️ STRUCTURAL RISK: No realistic path to break-even identified.")

    # Apply the Gate
    final_opportunity_score = base_score * survival_multiplier

    # Generate standard warnings
    if evidence_count < ResearchConfig.WARN_IF_EVIDENCE_BELOW:
        warnings.append(f"⚠️ Limited validation evidence ({evidence_count} sources).")
    if competitor_count > 10:
        warnings.append(f"⚠️ Highly competitive 'Red Ocean' market ({competitor_count} competitors).")
    if growth_pct < 0:
        warnings.append(f"⚠️ Market is shrinking ({growth_pct:.1f}% YoY).")

    # Determine final grade
    if final_opportunity_score >= 85: grade, conf = "A (Gold Mine)", "High"
    elif final_opportunity_score >= 70: grade, conf = "B (Solid Opportunity)", "Medium-High"
    elif final_opportunity_score >= 50: grade, conf = "C (Risky)", "Medium"
    else: grade, conf = "D (Not Recommended)", "Low"

    return {
        "opportunity_score": round(final_opportunity_score, 1),
        "grade": grade,
        "confidence": conf,
        "breakdown": {
            "base_score_before_penalties": round(base_score, 1),
            "survival_multiplier": survival_multiplier,
            "pain_score_raw": pain_score,
            "pain_score_adjusted": round(adjusted_pain_score, 1),
            "evidence_count": evidence_count,
            "evidence_quality": evidence_quality,
            "growth_pct": growth_pct,
            "growth_score": growth_score,
            "competitor_count": competitor_count,
            "competition_level": competition_data["level"],
            "competition_score": competition_score,
            "runway_months": runway if runway is not None else "Unknown",
            "break_even_month": break_even
        },
        "warnings": warnings,
        "recommendation": _generate_recommendation(final_opportunity_score, warnings)
    }

def _generate_recommendation(score: float, warnings: list) -> str:
    # [KEEP EXISTING RECOMMENDATION LOGIC]
    if score >= 85: return "Strong opportunity. Proceed with confidence but validate assumptions."
    elif score >= 70: return "Solid opportunity. Conduct additional validation before major investment."
    elif score >= 50: return "Risky opportunity. Only proceed if you have unique advantages or insights."
    else: return "Not recommended. Financial or market structure presents unacceptable risk."