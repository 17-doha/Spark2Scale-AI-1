# app/graph/market_research_agent/validation_layer.py
"""
REALISM VALIDATION LAYER
Add sanity checks and validation to prevent unrealistic outputs
"""

import re
from app.graph.market_research_agent.logger_config import get_logger

logger = get_logger("ValidationLayer")

# ============================================
# FINANCIAL VALIDATION
# ============================================

class FinancialValidator:
    """Validates financial projections for realism"""
    
    # Industry-specific sanity check ranges (in USD)
    SANITY_RANGES = {
        "SaaS": {
            "min_startup": 15000,
            "max_startup": 500000,
            "min_monthly": 1000,
            "max_monthly": 100000,
            "typical_cac_ltv": 3.0,
            "typical_margin": 0.70
        },
        "E-commerce": {
            "min_startup": 5000,
            "max_startup": 200000,
            "min_monthly": 500,
            "max_monthly": 50000,
            "typical_cac_ltv": 2.0,
            "typical_margin": 0.40
        },
        "Marketplace": {
            "min_startup": 20000,
            "max_startup": 300000,
            "min_monthly": 2000,
            "max_monthly": 80000,
            "typical_cac_ltv": 4.0,
            "typical_margin": 0.20
        },
        "Service": {
            "min_startup": 3000,
            "max_startup": 100000,
            "min_monthly": 500,
            "max_monthly": 30000,
            "typical_cac_ltv": 2.5,
            "typical_margin": 0.50
        },
        "Hardware": {
            "min_startup": 100000,
            "max_startup": 5000000,
            "min_monthly": 10000,
            "max_monthly": 500000,
            "typical_cac_ltv": 2.0,
            "typical_margin": 0.30
        }
    }
    
    @staticmethod
    def validate_startup_costs(total_startup, industry="SaaS"):
        """Check if startup costs are in reasonable range"""
        ranges = FinancialValidator.SANITY_RANGES.get(
            industry, 
            FinancialValidator.SANITY_RANGES["SaaS"]
        )
        
        warnings = []
        
        if total_startup < ranges["min_startup"]:
            warnings.append({
                "level": "HIGH",
                "message": f"Startup cost of ${total_startup:,} seems unrealistically LOW for {industry}. "
                          f"Typical minimum: ${ranges['min_startup']:,}. "
                          f"Consider: development costs, legal fees, initial marketing."
            })
        
        if total_startup > ranges["max_startup"]:
            warnings.append({
                "level": "MEDIUM",
                "message": f"Startup cost of ${total_startup:,} seems HIGH for MVP. "
                          f"Typical maximum: ${ranges['max_startup']:,}. "
                          f"Consider: starting lean, validating before building fully."
            })
        
        return warnings
    
    @staticmethod
    def validate_monthly_costs(total_monthly, industry="SaaS"):
        """Check if monthly costs are reasonable"""
        ranges = FinancialValidator.SANITY_RANGES.get(
            industry,
            FinancialValidator.SANITY_RANGES["SaaS"]
        )
        
        warnings = []
        
        if total_monthly < ranges["min_monthly"]:
            warnings.append({
                "level": "MEDIUM",
                "message": f"Monthly costs of ${total_monthly:,} seem LOW. "
                          f"Verify: hosting, tools, minimum marketing spend included."
            })
        
        if total_monthly > ranges["max_monthly"]:
            warnings.append({
                "level": "MEDIUM",
                "message": f"Monthly costs of ${total_monthly:,} seem HIGH for early stage. "
                          f"Consider: reducing burn rate until product-market fit."
            })
        
        return warnings
    
    @staticmethod
    def validate_revenue_assumptions(daily_customers, avg_price, industry="SaaS"):
        """Check if revenue assumptions are realistic"""
        warnings = []
        
        # Daily customer validation
        if daily_customers > 50:
            warnings.append({
                "level": "HIGH",
                "message": f"Assuming {daily_customers} customers/day from launch is UNREALISTIC. "
                          f"Most startups acquire 1-5 customers/day in first 3 months. "
                          f"Use growth curve: start at 2-5/day, grow to {daily_customers}/day over 12 months."
            })
        
        if daily_customers < 1:
            warnings.append({
                "level": "HIGH",
                "message": f"Less than 1 customer/day ({daily_customers}) may not be viable business. "
                          f"Re-evaluate market size or customer acquisition strategy."
            })
        
        # Pricing validation
        if avg_price < 1:
            warnings.append({
                "level": "MEDIUM",
                "message": f"Price of ${avg_price} is very low. "
                          f"Verify pricing strategy - may not cover CAC and operations."
            })
        
        if avg_price > 500 and industry == "SaaS":
            warnings.append({
                "level": "LOW",
                "message": f"Price of ${avg_price}/month is enterprise-level. "
                          f"Ensure sales cycle and CAC projections match enterprise sales reality."
            })
        
        # Monthly revenue reality check
        monthly_revenue = daily_customers * avg_price * 30
        
        if monthly_revenue > 100000 and daily_customers > 30:
            warnings.append({
                "level": "HIGH",
                "message": f"Projected ${monthly_revenue:,}/month from {daily_customers} daily customers "
                          f"is VERY OPTIMISTIC for early stage. "
                          f"Most startups take 12-24 months to reach this level."
            })
        
        return warnings
    
    @staticmethod
    def validate_profit_margin(revenue, costs, industry="SaaS"):
        """Check if profit margins are realistic"""
        if revenue == 0:
            return []
        
        margin = (revenue - costs) / revenue
        ranges = FinancialValidator.SANITY_RANGES.get(
            industry,
            FinancialValidator.SANITY_RANGES["SaaS"]
        )
        
        typical_margin = ranges["typical_margin"]
        warnings = []
        
        if margin > typical_margin + 0.20:  # More than 20% above typical
            warnings.append({
                "level": "MEDIUM",
                "message": f"Profit margin of {margin*100:.1f}% seems HIGH for {industry}. "
                          f"Typical margin: {typical_margin*100:.1f}%. "
                          f"Verify: all costs included (CAC, churn, support, overhead)?"
            })
        
        if margin < 0.10 and revenue > costs:  # Less than 10% margin
            warnings.append({
                "level": "MEDIUM",
                "message": f"Profit margin of {margin*100:.1f}% is VERY THIN. "
                          f"Business may struggle with this margin. Consider: "
                          f"raising prices or reducing costs."
            })
        
        return warnings


# ============================================
# MARKET SIZING VALIDATION
# ============================================

class MarketSizingValidator:
    """Validates TAM/SAM/SOM numbers"""
    
    # Maximum reasonable TAM by market scope
    MAX_TAM_RANGES = {
        "Global SaaS": 1_000_000_000_000,      # $1T
        "Global E-commerce": 5_000_000_000_000, # $5T
        "Regional SaaS": 100_000_000_000,      # $100B
        "Regional E-commerce": 500_000_000_000, # $500B
        "Country-specific": 50_000_000_000,    # $50B
        "City-specific": 5_000_000_000,        # $5B
        "Niche B2B": 10_000_000_000,          # $10B
        "Niche B2C": 1_000_000_000             # $1B
    }
    
    @staticmethod
    def extract_numeric_value(value_string):
        """Extract number from strings like '$5 Billion'"""
        try:
            # Remove currency symbols and commas
            clean = re.sub(r'[^\d.]', '', value_string.split()[0])
            num = float(clean)
            
            # Adjust for unit
            value_lower = value_string.lower()
            if 'trillion' in value_lower:
                num *= 1_000_000
            elif 'billion' in value_lower:
                num *= 1_000
            elif 'thousand' in value_lower:
                num *= 0.001
            # else: assume millions
            
            return num  # Returns in millions
        except:
            return None
    
    @staticmethod
    def validate_tam(tam_value_str, industry, geography):
        """Check if TAM is reasonable"""
        tam_millions = MarketSizingValidator.extract_numeric_value(tam_value_str)
        
        if not tam_millions:
            return [{
                "level": "HIGH",
                "message": "Could not parse TAM value. Verify market sizing data quality."
            }]
        
        warnings = []
        
        # Global market reasonableness
        if tam_millions > 10_000_000:  # > $10 Trillion
            warnings.append({
                "level": "HIGH",
                "message": f"TAM of {tam_value_str} exceeds reasonable global market size. "
                          f"Total global economy is ~$100T. Verify market definition."
            })
        
        # Check against scope
        scope_key = f"{geography} {industry}" if geography != "Global" else f"Global {industry}"
        max_reasonable = MarketSizingValidator.MAX_TAM_RANGES.get(
            scope_key,
            MarketSizingValidator.MAX_TAM_RANGES.get("Niche B2B", 10_000)
        )
        
        if tam_millions > max_reasonable:
            warnings.append({
                "level": "MEDIUM",
                "message": f"TAM of {tam_value_str} seems HIGH for {scope_key}. "
                          f"Typical maximum: ${max_reasonable:,}M. "
                          f"Verify: not mixing broader market (e.g., all smartphones vs new brands)."
            })
        
        return warnings
    
    @staticmethod
    def validate_sam_to_tam_ratio(tam_value_str, sam_value_str):
        """Check if SAM is reasonable % of TAM"""
        tam = MarketSizingValidator.extract_numeric_value(tam_value_str)
        sam = MarketSizingValidator.extract_numeric_value(sam_value_str)
        
        if not tam or not sam:
            return []
        
        ratio = sam / tam
        warnings = []
        
        if ratio > 0.50:  # SAM > 50% of TAM
            warnings.append({
                "level": "MEDIUM",
                "message": f"SAM ({sam_value_str}) is {ratio*100:.1f}% of TAM ({tam_value_str}). "
                          f"This seems HIGH. SAM should typically be 5-30% of TAM. "
                          f"Verify: geographic or segment narrowing is correctly applied."
            })
        
        if ratio < 0.01:  # SAM < 1% of TAM
            warnings.append({
                "level": "LOW",
                "message": f"SAM ({sam_value_str}) is only {ratio*100:.2f}% of TAM. "
                          f"Market may be too narrow. Consider: expanding target segment."
            })
        
        return warnings
    
    @staticmethod
    def validate_som_to_sam_ratio(sam_value_str, som_value_str):
        """Check if SOM is realistic % of SAM"""
        sam = MarketSizingValidator.extract_numeric_value(sam_value_str)
        som = MarketSizingValidator.extract_numeric_value(som_value_str)
        
        if not sam or not som:
            return []
        
        ratio = som / sam
        warnings = []
        
        if ratio > 0.10:  # SOM > 10% of SAM
            warnings.append({
                "level": "HIGH",
                "message": f"SOM ({som_value_str}) is {ratio*100:.1f}% of SAM ({sam_value_str}). "
                          f"Capturing 10%+ market share is VERY DIFFICULT for startups. "
                          f"Typical startup SOM: 0.5-5% of SAM. "
                          f"Adjust expectations or justify why you can capture this much."
            })
        
        if ratio < 0.001:  # SOM < 0.1% of SAM
            warnings.append({
                "level": "MEDIUM",
                "message": f"SOM ({som_value_str}) is only {ratio*100:.3f}% of SAM. "
                          f"While conservative, verify this is large enough for viable business. "
                          f"Minimum viable SOM: $100K-500K annually."
            })
        
        # Minimum viable SOM
        if som < 0.1:  # Less than $100K
            warnings.append({
                "level": "HIGH",
                "message": f"SOM of {som_value_str} (${som*1_000_000:,.0f}) may be too small for viable business. "
                          f"Consider: Is market opportunity large enough?"
            })
        
        return warnings


# ============================================
# GROWTH VALIDATION
# ============================================

class GrowthValidator:
    """Validates market growth projections"""
    
    @staticmethod
    def validate_growth_rate(growth_pct, source_name):
        """Check if growth rate is realistic"""
        warnings = []
        
        if growth_pct > 100:  # > 100% growth
            warnings.append({
                "level": "HIGH",
                "message": f"Growth rate of {growth_pct:.1f}% is EXTREME. "
                          f"Verify: Is this a temporary spike (fad) or sustained trend? "
                          f"Source: {source_name}. Check if seasonal or one-time event."
            })
        
        if growth_pct > 50:  # > 50% growth
            warnings.append({
                "level": "MEDIUM",
                "message": f"Growth rate of {growth_pct:.1f}% is very high. "
                          f"Verify sustainability. High growth often normalizes after 12-24 months."
            })
        
        if growth_pct < -20:  # Declining market
            warnings.append({
                "level": "HIGH",
                "message": f"Market is DECLINING at {growth_pct:.1f}% annually. "
                          f"High risk. Only enter if you have clear differentiation or pivot strategy."
            })
        
        if -5 < growth_pct < 5:  # Flat market
            warnings.append({
                "level": "MEDIUM",
                "message": f"Market growth is flat ({growth_pct:.1f}%). "
                          f"Growth will come from taking market share, not market expansion. "
                          f"Ensure strong competitive advantage."
            })
        
        return warnings
    
    @staticmethod
    def fix_growth_score_inflation(growth_pct):
        """
        FIX: Remove the +50 baseline inflation
        
        OLD formula: score = (growth_pct + 50) * 2
        This made 0% growth = 100 score ❌
        
        NEW formula: score = growth_pct + 50
        Now 0% growth = 50 score ✅
        """
        # Map -50% growth → 0, 0% → 50, +50% → 100
        score = max(0, min(100, growth_pct + 50))
        
        return {
            "growth_score": score,
            "interpretation": (
                "Explosive" if growth_pct > 50 else
                "High" if growth_pct > 20 else
                "Moderate" if growth_pct > 5 else
                "Slow" if growth_pct > 0 else
                "Flat" if growth_pct > -5 else
                "Declining"
            )
        }


# ============================================
# COMPREHENSIVE VALIDATOR
# ============================================

class ReportValidator:
    """Main validator that runs all checks"""
    
    @staticmethod
    def validate_complete_report(report_data):
        """
        Run all validation checks and return comprehensive warnings
        
        Args:
            report_data: Dict with all generated data
        
        Returns:
            Dict with warnings organized by severity
        """
        all_warnings = {
            "HIGH": [],     # Critical issues
            "MEDIUM": [],   # Should review
            "LOW": []       # Nice to know
        }
        
        # Financial validation
        if "finance" in report_data:
            finance = report_data["finance"]
            industry = report_data.get("industry", "SaaS")
            
            # Validate startup costs
            total_startup = sum(finance.get("startup_costs", {}).values())
            warnings = FinancialValidator.validate_startup_costs(total_startup, industry)
            for w in warnings:
                all_warnings[w["level"]].append(w["message"])
            
            # Validate monthly costs
            total_monthly = sum(finance.get("monthly_fixed_costs", {}).values())
            warnings = FinancialValidator.validate_monthly_costs(total_monthly, industry)
            for w in warnings:
                all_warnings[w["level"]].append(w["message"])
            
            # Validate revenue assumptions
            rev = finance.get("revenue_assumptions", {})
            warnings = FinancialValidator.validate_revenue_assumptions(
                rev.get("daily_customers", 0),
                rev.get("avg_ticket_price", 0),
                industry
            )
            for w in warnings:
                all_warnings[w["level"]].append(w["message"])
        
        # Market sizing validation
        if "market_sizing" in report_data:
            sizing = report_data["market_sizing"]
            industry = report_data.get("industry", "SaaS")
            geography = report_data.get("geography", "Global")
            
            # Validate TAM
            warnings = MarketSizingValidator.validate_tam(
                sizing.get("tam_value", "Unknown"),
                industry,
                geography
            )
            for w in warnings:
                all_warnings[w["level"]].append(w["message"])
            
            # Validate SAM/TAM ratio
            warnings = MarketSizingValidator.validate_sam_to_tam_ratio(
                sizing.get("tam_value", "Unknown"),
                sizing.get("sam_value", "Unknown")
            )
            for w in warnings:
                all_warnings[w["level"]].append(w["message"])
            
            # Validate SOM/SAM ratio
            warnings = MarketSizingValidator.validate_som_to_sam_ratio(
                sizing.get("sam_value", "Unknown"),
                sizing.get("som_value", "Unknown")
            )
            for w in warnings:
                all_warnings[w["level"]].append(w["message"])
        
        # Growth validation
        if "trends" in report_data:
            trends = report_data["trends"]
            growth_pct = trends.get("growth_pct", 0)
            source = trends.get("source", "Unknown")
            
            warnings = GrowthValidator.validate_growth_rate(growth_pct, source)
            for w in warnings:
                all_warnings[w["level"]].append(w["message"])
        
        return all_warnings
    
    @staticmethod
    def format_warnings_for_report(warnings_dict):
        """Format warnings for inclusion in report"""
        output = []
        
        if warnings_dict["HIGH"]:
            output.append("## 🚨 CRITICAL WARNINGS\n")
            for w in warnings_dict["HIGH"]:
                output.append(f"- {w}\n")
        
        if warnings_dict["MEDIUM"]:
            output.append("\n## ⚠️ IMPORTANT NOTES\n")
            for w in warnings_dict["MEDIUM"]:
                output.append(f"- {w}\n")
        
        if warnings_dict["LOW"]:
            output.append("\n## ℹ️ CONSIDERATIONS\n")
            for w in warnings_dict["LOW"]:
                output.append(f"- {w}\n")
        
        return "".join(output)