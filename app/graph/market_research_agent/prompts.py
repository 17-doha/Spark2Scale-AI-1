# app/graph/market_research_agent/prompts.py
"""
Enhanced prompts for realistic market research analysis
"""

MARKET_RESEARCH_SYSTEM_PROMPT = """
You are a top-tier market researcher. Analyze the market trends, competitors, and potential opportunities.
"""

def generate_research_plan_prompt(idea, problem):
    return f"""
    ROLE: Lead Market Researcher.
    GOAL: Plan the entire research strategy for "{idea}" (Problem: "{problem}").
    
    TASK: Generate a JSON object containing ALL necessary search parameters.
    
    OUTPUT STRUCTURE (Strict JSON):
    {{
        "competitor_queries": ["query1", "query2 (vs/alternatives)"],
        "validation_queries": {{
            "problem": ["query1 (reddit/forum)"],
            "solution": ["query1 (reviews/feedback)"]
        }},
        "market_identity": {{
            "industry": "Industry Name",
            "wikipedia_topic": "Wikipedia_Title_With_Underscores",
            "target_country": "Detect from idea or default 'Global'",
            "currency_code": "USD/EGP/etc",
            "currency_symbol": "$"
        }},
        "financial_queries": ["salary query", "rent query"]
    }}
    
    RULES:
    1. Competitor Queries: Focus on finding specific app names (e.g., "{idea} alternatives").
    2. Wikipedia Topic: Must be a valid existing article title (e.g. "Online_dating_service").
    3. Country: If idea implies a location (e.g. "in Cairo"), use it. Else Global/US.
    4. Financials: tailored to the detected country.
    """

def generate_smart_queries_prompt(business_idea):
    return f"""
    Business Idea: "{business_idea}"
    Generate 5 Google Search Queries to find SPECIFIC COMPETITOR APP NAMES.
    Focus on: "alternatives to", "vs", "pricing", "features", "reviews".
    RETURN JSON list of strings.
    """

def extract_competitors_prompt(business_idea, search_data_text):
    return f"""
    You are a Data Cleaner.
    Topic: "{business_idea}"
    Search Results:
    {search_data_text}
    
    TASK: List the top 5-8 DIRECT COMPETITORS (Company/App Names Only).
    
    CRITICAL RULES:
    1. DO NOT return article titles (e.g. "Top 10 Apps"). Extract the APP NAME inside (e.g. "Tinder").
    2. DO NOT return generic terms (e.g. "AI Dating").
    3. EXTRACT 3-5 KEY FEATURES for each competitor.
    4. If less than 5 real competitors found, return what you find (don't make up names).
    
    RETURN JSON List:
    [
        {{ "Name": "App Name", "Features": "Feature A, Feature B, Feature C" }},
        {{ "Name": "App Name", "Features": "Feature C, Feature D, Feature E" }}
    ]
    """

def generate_validation_queries_prompt(idea, problem_statement):
    return f"""
    Idea: {idea} 
    Problem: {problem_statement}
    
    Generate search queries to validate this problem EXISTS and people are ACTIVELY seeking solutions.
    
    RETURN JSON with TWO categories:
    {{
        "problem_queries": [
            "site:reddit.com {problem_statement}",
            "site:twitter.com frustrated with {problem_statement}",
            "site:quora.com need help with {problem_statement}"
        ],
        "solution_queries": [
            "site:producthunt.com {idea} alternatives",
            "site:g2.com {idea} reviews",
            "site:trustpilot.com similar to {idea}"
        ]
    }}
    
    Make queries specific and focused on REAL USER PAIN and EXISTING SOLUTIONS.
    """

def analyze_pain_points_prompt(idea, problem_statement, evidence):
    formatted_evidence = evidence
    if isinstance(evidence, list):
        formatted_evidence = "\n".join([str(e) for e in evidence])

    return f"""
    You are a rigorous market validation analyst. Be REALISTIC and EVIDENCE-BASED.
    
    HYPOTHESIS: '{idea}' solves '{problem_statement}'.
    
    EVIDENCE FROM MULTIPLE SOURCES: 
    {formatted_evidence}
    
    TASK:
    1. Assign a RAW PAIN SCORE (0-100) based on evidence intensity.
       - 0-20: Mild inconvenience, "nice to have"
       - 20-40: Annoying but people work around it
       - 40-60: Moderate pain, people complain but manage
       - 60-80: Significant pain, people actively seek solutions
       - 80-100: Urgent, expensive, emotional problem (desperation signals)
    
    2. Evaluate SOLUTION FIT: Does the proposed idea actually solve the problem found?
       - High: Direct solution to validated pain
       - Medium: Partial solution or indirect approach
       - Low: Mismatch between problem and solution
    
    3. Evidence Quality Check:
       - Are these real user complaints or just hypothetical?
       - How recent is the evidence?
       - Multiple independent sources or just one?
    
    CRITICAL: Be CONSERVATIVE. If evidence is weak, score should be LOW (20-40).
    Only give 70+ if there are MULTIPLE sources showing INTENSE, RECENT pain.
    
    OUTPUT JSON: 
    {{ 
        "verdict": "VALIDATED/MODERATE/WEAK/INSUFFICIENT_DATA", 
        "pain_score": 0,
        "pain_score_reasoning": "Detailed explanation: Why this score? What signals did you see? Quote specific evidence.",
        "solution_fit_score": "High/Medium/Low",
        "solution_fit_reasoning": "Does the proposed solution actually address the pain points found?",
        "reasoning": "Overall assessment with evidence quality evaluation",
        "evidence_quality_notes": "How many sources? How recent? How credible?"
    }}
    """

def identify_industry_prompt(idea):
    return f"Identify the broader 'Industry' for: '{idea}'. Return ONLY the string (e.g. 'Online Dating Services')."

def wiki_fallback_prompt(query):
    return f"""
    Task: Identify the main Wikipedia Article Title for the industry of: "{query}".
    Examples:
    - "Cat Cafe" -> "Cat_café"
    - "AI Dating App" -> "Online_dating_service"
    - "Solar Panels" -> "Solar_power"
    
    RETURN ONLY THE TITLE STRING (No quotes, use underscores for spaces).
    """

def analyze_market_size_prompt(idea, industry, location, market_data):
    return f"""
    You are a Market Sizing Expert. Be REALISTIC and cite sources.
    
    IDEA: {idea}
    INDUSTRY: {industry}
    LOCATION: {location}
    SEARCH DATA: 
    {market_data}
    
    TASK: Estimate TAM, SAM, and SOM using ACTUAL DATA from the search results.
    
    DEFINITIONS:
    - TAM (Total Addressable Market): Total market revenue for this industry/location
    - SAM (Serviceable Available Market): The segment you can realistically serve
    - SOM (Serviceable Obtainable Market): What you can capture as a startup (typically 1-5% of SAM)
    
    CRITICAL RULES:
    1. USE THE DATA: Quote actual market research reports, industry analyses, or credible sources
    2. Be CONSERVATIVE: If data is unclear, estimate on the low side
    3. SAM should be a realistic subset of TAM (not 90% of TAM unless you have proof)
    4. SOM should be 1-5% of SAM for a new startup (not 20-30%)
    5. If you can't find data, say "Insufficient data" - don't make up numbers
    
    Also analyze:
    - RED vs BLUE OCEAN: Count competitors from search results
    - SCALABILITY: Software = High, Service/Physical = Medium/Low
    
    RETURN JSON:
    {{
        "tam_value": "$X Billion" or "Insufficient data",
        "tam_description": "Source: [cite report]. Context for TAM...",
        "sam_value": "$X Million" or "Insufficient data",
        "sam_description": "How we narrowed from TAM (geography, segment, etc)",
        "som_value": "$X Million" (1-5% of SAM),
        "som_description": "Conservative startup capture estimate",
        "market_type": "Red Ocean (X competitors found) / Blue Ocean (few competitors)",
        "scalability_score": "High/Medium/Low",
        "scalability_reasoning": "Why...",
        "data_quality": "High/Medium/Low - based on source credibility",
        "sources": ["Exact source names with credibility ratings"]
    }}
    
    If search data is insufficient, indicate this clearly in the response.
    """

def detect_currency_prompt(idea):
    return f"""
    Analyze this business idea: "{idea}"
    RETURN JSON: {{ "country": "CountryName", "currency_code": "XXX", "currency_symbol": "$" }}
    """

def financial_plan_prompt(idea, country, currency_code):
    return f"""
    Business: "{idea}"
    Location: {country}
    Currency: {currency_code}
    
    TASK: Generate 4-5 SPECIFIC search queries to find real-world numeric cost data.
    Focus on ACTUAL NUMBERS not generic info.
    
    Query categories:
    1. Salary data: "average [role] salary {country} 2024" (e.g., software engineer, marketing manager)
    2. Infrastructure costs: "AWS pricing", "office rent {country} per sqm 2024"
    3. Customer acquisition: "{idea} customer acquisition cost", "CAC for [industry] startups"
    4. Legal/compliance: "business license cost {country}", "LLC formation fees {country}"
    
    RETURN JSON list of strings with SPECIFIC, DATA-FOCUSED queries.
    Example: ["software developer salary Egypt 2024", "AWS startup pricing tier"]
    """

def financial_extraction_prompt(idea, market_data, currency_code):
    return f"""
    You are a Conservative CFO analyzing startup costs.
    
    BUSINESS: {idea}
    MARKET DATA: {market_data}
    CURRENCY: {currency_code}
    
    TASK: Build a REALISTIC Financial Estimate based ONLY on the MARKET DATA above.
    
    CRITICAL RULES:
    1. USE THE DATA: If search results show rent is $20/sqm, USE that number
    2. CITE SOURCES: Mention where each number came from
    3. CONSERVATIVE BIAS:
       - Costs: Use UPPER end of ranges found
       - Revenue: Use LOWER end of estimates
       - If no data: Use industry benchmarks (favor higher costs)
    4. REALISM:
       - Marketing should be 20-40% of revenue (not 5%)
       - Salaries must match local data (don't lowball)
       - Include contingency (10-20% of total)
    5. NO GUESSING: If data is missing, clearly state "estimate based on industry benchmark"
    
    REVENUE ASSUMPTIONS:
    - Research competitor pricing from the data
    - Estimate realistic customer counts (be conservative)
    - Don't assume instant traction
    
    RETURN JSON (No Markdown):
    {{
        "currency": "{currency_code}",
        "startup_costs": {{
            "development_app_website": 0,
            "legal_licenses": 0,
            "marketing_launch_campaign": 0,
            "office_equipment_rent": 0,
            "contingency_fund": 0
        }},
        "monthly_fixed_costs": {{
            "server_cloud_infrastructure": 0,
            "marketing_ad_spend": 0,
            "salaries_staff": 0,
            "utilities_tools_misc": 0
        }},
        "revenue_assumptions": {{
            "avg_ticket_price": 0, 
            "daily_customers": 0,
            "assumptions_notes": "Based on [source]. Conservative estimate."
        }},
        "sources_used": ["Exact source names from market_data with numbers cited"],
        "data_quality": "High/Medium/Low - based on how much real data was found"
    }}
    """

def investment_memo_prompt_enhanced(query, pain_score, growth_pct, grade, opp_score, 
                                   finance_summary, val_data, breakdown, warnings, 
                                   recommendation, evidence_count, competitor_count):
    return f"""
    You are an AI Market Research Engine writing an objective investment memo.
    
    TOPIC: {query}
    
    EXECUTIVE DASHBOARD:
    - Opportunity Score: {opp_score:.1f}/100 ({grade})
    - Pain Score: {pain_score:.1f}/100 (Evidence: {evidence_count} sources)
    - Market Growth: {growth_pct:.1f}% YoY
    - Competition Level: {breakdown['competition_level']} ({competitor_count} competitors)
    
    SCORE BREAKDOWN:
    - Pain Component: {breakdown['pain_score_adjusted']:.1f} (weight: 35%)
    - Growth Component: {breakdown['growth_score']:.1f} (weight: 25%)
    - Market Size Component: Calculated from TAM/SAM data (weight: 25%)
    - Competition Component: {breakdown['competition_score']:.1f} (weight: 15%)
    
    FINANCIAL PROJECTIONS: 
    {finance_summary}
    
    VALIDATION EVIDENCE: 
    {val_data}
    
    WARNINGS & RISKS:
    {chr(10).join(warnings) if warnings else "No major warnings"}
    
    RECOMMENDATION:
    {recommendation}
    
    INSTRUCTIONS:
    Write a comprehensive, OBJECTIVE Investment Memo using THIRD-PERSON language.
    
    TONE REQUIREMENTS:
    1. Use "The analysis indicates...", "Data suggests...", "Research shows..."
    2. NEVER use "I", "we", "my", "our"
    3. Be REALISTIC - acknowledge risks and uncertainties
    4. Cite the scores and evidence counts in your analysis
    5. If evidence is weak (< 5 sources), acknowledge this limitation
    
    STRUCTURE:
    1. **Executive Summary** (2-3 paragraphs)
       - Overall opportunity assessment
       - Key finding highlights
       - Final verdict (Recommended / Conditional / Not Recommended)
    
    2. **Market Opportunity Analysis**
       - Growth trends ({growth_pct:.1f}% - what does this mean?)
       - Market size potential
       - Scalability assessment
    
    3. **Problem Validation**
       - Pain score interpretation ({pain_score}/100 from {evidence_count} sources)
       - Evidence quality assessment
       - Customer need intensity
    
    4. **Competitive Landscape**
       - Competition level ({competitor_count} competitors)
       - Market positioning analysis
       - Differentiation opportunities/challenges
    
    5. **Financial Viability**
       - Startup cost assessment
       - Revenue potential
       - Break-even analysis
       - Capital efficiency
    
    6. **Risk Factors**
       - Evidence limitations
       - Market risks
       - Competitive threats
       - Execution challenges
    
    7. **Final Recommendation**
       - Clear go/no-go guidance
       - Conditions for success
       - Next steps for validation
    
    Use **bold** for key metrics and findings.
    Be honest about data limitations and uncertainties.
    """

def trend_analysis_prompt(growth_pct, source, trend_data=""):
    return f"""
    You are a Senior Market Strategist.
    DATA:
    - 12-Month Growth: {growth_pct:.1f}%
    - Source: {source}
    - Recent Trend Data Points: {trend_data}

    TASK: Write a 3-4 sentence detailed analysis of this trend for a report caption.
    
    BE REALISTIC:
    - Sentence 1: Interpret the growth rate (explosive >50%, strong 20-50%, moderate 5-20%, flat/declining <5%)
    - Sentence 2: Explain possible drivers based on the numbers
    - Sentence 3: Assess implications for new entrants (opportunity vs saturation)
    - FORMATTING: Use **double asterisks** to bold 2-3 key phrases

    If growth is negative or near zero, acknowledge the challenging market conditions.
    
    RETURN ONLY THE PARAGRAPH. No intro/outro.
    """

def financial_analysis_prompt(startup_total, currency, break_even_month, net_profit):
    return f"""
    You are a Senior Financial Consultant.
    DATA:
    - Total Startup Cost: {startup_total:,.0f} {currency}
    - Break-Even Point: Month {break_even_month}
    - Monthly Net Profit (Projected): {net_profit:,.0f} {currency}

    TASK: Write a 3-4 sentence financial health assessment for a report caption.
    
    BE REALISTIC:
    - Sentence 1: Evaluate capital requirements (Low <$25K, Medium $25-100K, High >$100K)
    - Sentence 2: Assess break-even timeline (Fast <6mo, Moderate 6-12mo, Slow >12mo)
    - Sentence 3: Comment on margin sustainability and cash burn risk
    - FORMATTING: Use **double asterisks** to bold key insights

    If numbers seem unrealistic (too optimistic or pessimistic), note this.
    
    RETURN ONLY THE PARAGRAPH. No intro/outro.
    """
