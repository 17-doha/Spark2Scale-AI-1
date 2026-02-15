# app/graph/market_research_agent/helpers/market_sizing_validator.py
"""
Realistic Market Sizing Validator
Validates and corrects TAM/SAM/SOM calculations to prevent unrealistic numbers
"""

import re
from app.core.logger import get_logger

logger = get_logger("MarketSizingValidator")


class RealisticMarketSizer:
    """
    Calculates realistic TAM/SAM/SOM with validation and correction
    """
    
    # Maximum reasonable TAM by industry (in millions USD)
    MAX_REASONABLE_TAM = {
        "SaaS": 500_000,           # $500B max for global SaaS
        "Software": 500_000,
        "E-commerce": 5_000_000,   # $5T for global e-commerce
        "FinTech": 1_000_000,      # $1T for fintech
        "Finance": 1_000_000,
        "HealthTech": 500_000,     # $500B for healthtech
        "Healthcare": 500_000,
        "EdTech": 300_000,         # $300B for edtech
        "Education": 300_000,
        "Gaming": 200_000,         # $200B for gaming
        "Food Delivery": 500_000,  # $500B for food delivery
        "Food": 500_000,
        "Logistics": 1_000_000,    # $1T for logistics
        "Transportation": 1_000_000,
        "Hardware": 2_000_000,     # $2T for consumer hardware
        "Mobile": 2_000_000,
        "Retail": 3_000_000,       # $3T for retail
        "Default": 500_000         # $500B default
    }
    
    # Realistic SAM percentages of TAM by geography
    SAM_RATIOS = {
        "Global": 1.0,           # 100% if truly global
        "World": 1.0,
        "Worldwide": 1.0,
        "North America": 0.35,   # 35% of global
        "USA": 0.25,
        "United States": 0.25,
        "Canada": 0.04,
        "Europe": 0.25,          # 25% of global
        "EU": 0.25,
        "Asia": 0.30,            # 30% of global
        "China": 0.18,
        "India": 0.08,
        "Middle East": 0.05,     # 5% of global
        "GCC": 0.03,
        "Africa": 0.03,          # 3% of global
        "Latin America": 0.08,   # 8% of global
        "Egypt": 0.005,          # 0.5% of global
        "UAE": 0.008,            # 0.8% of global
        "Saudi Arabia": 0.012,   # 1.2% of global
        "UK": 0.04,              # 4% of global
        "Germany": 0.05,         # 5% of global
        "France": 0.04,          # 4% of global
        "Japan": 0.06,           # 6% of global
        "Country": 0.03,         # 3% for average country
        "City": 0.005,           # 0.5% for city
        "Cairo": 0.002,          # 0.2% for Cairo
        "Dubai": 0.003,          # 0.3% for Dubai
    }
    
    # Realistic SOM ranges (startup market capture)
    SOM_RANGES = {
        "Winner-Take-All": (0.001, 0.005),   # 0.1-0.5% (social networks, search)
        "Concentrated": (0.005, 0.02),       # 0.5-2% (cloud, payments)
        "Competitive": (0.01, 0.05),         # 1-5% (SaaS, apps)
        "Fragmented": (0.05, 0.15),          # 5-15% (restaurants, local services)
        "Default": (0.01, 0.03)              # 1-3% default
    }
    
    @staticmethod
    def extract_number_from_text(text):
        """
        Extract numeric value from text like '$5 Billion' or '500M'
        Returns value in millions USD
        """
        if not text or text == "Unknown" or text == "Insufficient data":
            return None
        
        try:
            # Remove currency symbols and commas
            text_lower = text.lower()
            
            # Extract the number
            number_match = re.search(r'[\d,\.]+', text)
            if not number_match:
                return None
            
            num = float(number_match.group().replace(',', ''))
            
            # Apply multiplier based on unit
            if 'trillion' in text_lower or text_lower.strip().endswith('t'):
                num *= 1_000_000  # Convert to millions
            elif 'billion' in text_lower or text_lower.strip().endswith('b'):
                num *= 1_000  # Convert to millions
            elif 'million' in text_lower or text_lower.strip().endswith('m'):
                pass  # Already in millions
            elif 'thousand' in text_lower or text_lower.strip().endswith('k'):
                num *= 0.001  # Convert to millions
            else:
                # Assume millions if no unit specified
                pass
            
            return num
        except Exception as e:
            logger.warning(f"Could not parse number from: {text} - {e}")
            return None
    
    @staticmethod
    def get_industry_key(industry):
        """Get the matching industry key from MAX_REASONABLE_TAM"""
        industry_lower = industry.lower()
        
        for key in RealisticMarketSizer.MAX_REASONABLE_TAM.keys():
            if key.lower() in industry_lower or industry_lower in key.lower():
                return key
        
        return "Default"
    
    @staticmethod
    def get_geography_key(location):
        """Get the matching geography key from SAM_RATIOS"""
        location_lower = location.lower()
        
        for key in RealisticMarketSizer.SAM_RATIOS.keys():
            if key.lower() in location_lower or location_lower in key.lower():
                return key
        
        return "Country"  # Default to average country
    
    @staticmethod
    def validate_and_correct_tam(tam_value, industry, geography):
        """
        Validate TAM and correct if unrealistic
        
        Returns: (corrected_tam_millions, correction_reason)
        """
        tam_millions = RealisticMarketSizer.extract_number_from_text(tam_value)
        
        if tam_millions is None:
            return None, "Could not parse TAM value"
        
        # Get max reasonable TAM for this industry
        industry_key = RealisticMarketSizer.get_industry_key(industry)
        max_reasonable = RealisticMarketSizer.MAX_REASONABLE_TAM[industry_key]
        
        corrections = []
        
        # Check 1: Exceeds industry maximum
        if tam_millions > max_reasonable:
            corrections.append(
                f"Original TAM ${tam_millions:,.0f}M exceeds reasonable max "
                f"for {industry} (${max_reasonable:,.0f}M)"
            )
            tam_millions = max_reasonable * 0.5  # Use 50% of max as conservative estimate
        
        # Check 2: Exceeds global economy size
        if tam_millions > 10_000_000:  # $10 Trillion
            corrections.append(
                f"Original TAM ${tam_millions:,.0f}M exceeds reasonable global market size"
            )
            tam_millions = max_reasonable * 0.3
        
        # Check 3: Geography-specific correction
        geo_key = RealisticMarketSizer.get_geography_key(geography)
        
        if geo_key not in ["Global", "World", "Worldwide"] and tam_millions > max_reasonable * 0.5:
            corrections.append(
                f"TAM seems too high for {geography}. Likely using global number."
            )
            # Apply geographic multiplier to TAM as well
            geo_ratio = RealisticMarketSizer.SAM_RATIOS[geo_key]
            tam_millions = tam_millions * geo_ratio * 2  # 2x geo_ratio for TAM (SAM will reduce further)
        
        correction_reason = "; ".join(corrections) if corrections else None
        
        return tam_millions, correction_reason
    
    @staticmethod
    def calculate_realistic_sam(tam_millions, geography, segment=None):
        """
        Calculate SAM as realistic subset of TAM
        
        Args:
            tam_millions: TAM in millions
            geography: Target geography
            segment: Optional segment (e.g., "small businesses", "millennials")
        
        Returns: (sam_millions, reasoning)
        """
        if not tam_millions:
            return None, "TAM not available"
        
        # Base geographic reduction
        geo_key = RealisticMarketSizer.get_geography_key(geography)
        geo_ratio = RealisticMarketSizer.SAM_RATIOS[geo_key]
        sam_millions = tam_millions * geo_ratio
        
        reasoning_parts = [f"Geographic focus on {geography} ({geo_ratio*100:.1f}% of TAM)"]
        
        # Additional segment reduction if specified
        if segment:
            # Typical segment is 10-30% of geographic market
            segment_ratio = 0.20  # Default 20%
            sam_millions *= segment_ratio
            reasoning_parts.append(f"Targeting {segment} segment (~{segment_ratio*100:.0f}% of market)")
        
        # Ensure SAM is not too close to TAM (unless truly global)
        if geo_key in ["Global", "World", "Worldwide"] and sam_millions / tam_millions > 0.7:
            sam_millions = tam_millions * 0.5
            reasoning_parts.append("Adjusted to 50% of TAM (not all segments addressable)")
        
        reasoning = ". ".join(reasoning_parts)
        
        return sam_millions, reasoning
    
    @staticmethod
    def determine_market_structure(competitor_count):
        """
        Determine market structure based on competitor analysis
        """
        if competitor_count <= 2:
            return "Winner-Take-All"
        elif competitor_count <= 5:
            return "Concentrated"
        elif competitor_count <= 15:
            return "Competitive"
        else:
            return "Fragmented"
    
    @staticmethod
    def calculate_realistic_som(sam_millions, market_structure, has_funding=False):
        """
        Calculate SOM as realistic startup capture
        
        Args:
            sam_millions: SAM in millions
            market_structure: Winner-Take-All, Concentrated, Competitive, Fragmented
            has_funding: Whether startup has significant funding
        
        Returns: (som_millions, reasoning)
        """
        if not sam_millions:
            return None, "SAM not available"
        
        # Get range for this market structure
        min_pct, max_pct = RealisticMarketSizer.SOM_RANGES.get(
            market_structure,
            RealisticMarketSizer.SOM_RANGES["Default"]
        )
        
        # Use middle of range, or higher end if well-funded
        if has_funding:
            som_pct = (min_pct + max_pct) / 2 + (max_pct - min_pct) * 0.25  # 75% of range
        else:
            som_pct = (min_pct + max_pct) / 2  # Middle of range
        
        som_millions = sam_millions * som_pct
        
        # Minimum viable SOM check
        if som_millions < 0.1:  # Less than $100K
            som_millions = 0.1
            reasoning = (
                f"Market structure: {market_structure}. "
                f"Typical startup capture: {som_pct*100:.2f}%. "
                f"WARNING: Below minimum viable market size ($100K) - may not be sustainable business."
            )
        else:
            reasoning = (
                f"Market structure: {market_structure}. "
                f"Realistic startup capture: {som_pct*100:.2f}% of SAM. "
                f"Conservative estimate for new entrant."
            )
        
        return som_millions, reasoning
    
    @staticmethod
    def format_value(millions):
        """Format millions into readable string"""
        if millions is None:
            return "Insufficient data"
        
        if millions >= 1_000_000:
            return f"${millions/1_000_000:.1f} Trillion"
        elif millions >= 1_000:
            return f"${millions/1_000:.1f} Billion"
        elif millions >= 1:
            return f"${millions:.1f} Million"
        else:
            return f"${millions*1000:.0f} Thousand"