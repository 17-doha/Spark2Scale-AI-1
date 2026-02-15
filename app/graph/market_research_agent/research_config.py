# app/graph/market_research_agent/research_config.py
"""
Configuration for Market Research Agent - Controls realism and quality thresholds
"""

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


# Helper Functions
def get_evidence_quality(evidence_count: int) -> tuple[str, float]:
    """Returns quality level and multiplier based on evidence count"""
    if evidence_count >= 10:
        return "very_strong", ResearchConfig.EVIDENCE_MULTIPLIERS["very_strong"]
    elif evidence_count >= 8:
        return "strong", ResearchConfig.EVIDENCE_MULTIPLIERS["strong"]
    elif evidence_count >= 5:
        return "moderate", ResearchConfig.EVIDENCE_MULTIPLIERS["moderate"]
    elif evidence_count >= 3:
        return "weak", ResearchConfig.EVIDENCE_MULTIPLIERS["weak"]
    else:
        return "minimal", ResearchConfig.EVIDENCE_MULTIPLIERS["minimal"]


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


def get_industry_benchmark(industry: str) -> dict:
    """Returns industry-specific benchmarks or default"""
    return ResearchConfig.INDUSTRY_BENCHMARKS.get(
        industry, 
        ResearchConfig.INDUSTRY_BENCHMARKS["Default"]
    )


def calculate_realistic_opportunity_score(
    pain_score: float,
    growth_pct: float,
    market_size_score: float,
    competitor_count: int,
    evidence_count: int
) -> dict:
    """
    Calculate opportunity score with realistic weighting and adjustments
    
    Returns:
        dict with score, grade, warnings, and breakdown
    """
    # Adjust pain score based on evidence quality
    evidence_quality, evidence_multiplier = get_evidence_quality(evidence_count)
    adjusted_pain_score = pain_score * evidence_multiplier
    
    # Convert growth % to score (0-100 scale)
    # -50% growth = 0, +50% growth = 100
    growth_score = max(0, min(100, (growth_pct + 50) * 2))
    
    # Get competition penalty
    competition_data = get_competition_level(competitor_count)
    competition_score = 100 * competition_data["multiplier"]
    
    # Calculate weighted score
    opportunity_score = (
        adjusted_pain_score * ResearchConfig.PAIN_WEIGHT +
        growth_score * ResearchConfig.GROWTH_WEIGHT +
        market_size_score * ResearchConfig.MARKET_SIZE_WEIGHT +
        competition_score * ResearchConfig.COMPETITION_WEIGHT
    )
    
    # Determine grade
    if opportunity_score >= ResearchConfig.GRADE_A_THRESHOLD:
        grade = "A (Gold Mine)"
        confidence = "High"
    elif opportunity_score >= ResearchConfig.GRADE_B_THRESHOLD:
        grade = "B (Solid Opportunity)"
        confidence = "Medium-High"
    elif opportunity_score >= ResearchConfig.GRADE_C_THRESHOLD:
        grade = "C (Risky)"
        confidence = "Medium"
    else:
        grade = "D (Not Recommended)"
        confidence = "Low"
    
    # Generate warnings
    warnings = []
    if evidence_count < ResearchConfig.WARN_IF_EVIDENCE_BELOW:
        warnings.append(f"⚠️ Limited evidence ({evidence_count} sources). Results may be unreliable.")
    
    if evidence_multiplier < 0.7:
        warnings.append(f"⚠️ Evidence quality is {evidence_quality}. Increase data collection for accuracy.")
    
    if competitor_count > 10:
        warnings.append(f"⚠️ Highly competitive market ({competitor_count} competitors). Differentiation critical.")
    
    if growth_pct < 0:
        warnings.append(f"⚠️ Market is declining ({growth_pct:.1f}%). High risk.")
    
    return {
        "opportunity_score": round(opportunity_score, 1),
        "grade": grade,
        "confidence": confidence,
        "breakdown": {
            "pain_score_raw": pain_score,
            "pain_score_adjusted": round(adjusted_pain_score, 1),
            "evidence_quality": evidence_quality,
            "evidence_count": evidence_count,
            "growth_score": round(growth_score, 1),
            "growth_pct": growth_pct,
            "market_size_score": market_size_score,
            "competition_level": competition_data["level"],
            "competition_score": round(competition_score, 1),
            "competitor_count": competitor_count
        },
        "warnings": warnings,
        "recommendation": _generate_recommendation(opportunity_score, warnings)
    }


def _generate_recommendation(score: float, warnings: list) -> str:
    """Generate action recommendation based on score and warnings"""
    if score >= 85:
        base = "Strong opportunity. Proceed with confidence but validate assumptions."
    elif score >= 70:
        base = "Solid opportunity. Conduct additional validation before major investment."
    elif score >= 50:
        base = "Risky opportunity. Only proceed if you have unique advantages or insights."
    else:
        base = "Not recommended. Consider pivoting or finding a different market."
    
    if warnings:
        base += f" Address {len(warnings)} concern(s) identified."
    
    return base