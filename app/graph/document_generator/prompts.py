from langchain_core.prompts import ChatPromptTemplate

# -----------------------------------------------------------------------------
# SWOT DOCUMENT GENERATION PROMPT
# -----------------------------------------------------------------------------
SWOT_GENERATION_PROMPT = """
You are an expert strategic business consultant generating a professional SWOT Analysis document.
Your task is to produce a beautifully formatted Markdown document following the same aesthetic theme as the Market Research Report.

Use the provided extracted context to build four distinct sections: Strengths, Weaknesses, Opportunities, and Threats.
Expand on the provided context logically to create a compelling, realistic, and professional document. 
If a quadrant has sparse context, use logical deduction based on the idea name and available data to fill it out realistically, but clearly distinguish between data-backed points and logical inferences.

Context from Market Research:
Idea Name: {idea_name}
Executive Summary Snapshot: {executive_summary}

Extracted Strengths Context:
{strengths_context}

Extracted Weaknesses Context:
{weaknesses_context}

Extracted Opportunities Context:
{opportunities_context}

Extracted Threats Context:
{threats_context}

Format Requirements:
1. Start with a main title `# SWOT Analysis: [Idea Name]`
2. Provide a brief introduction paragraph explaining the strategic position of the product/service.
3. Use `##` for each quadrant (e.g., `## 🏆 Strengths (Internal)`). Use relevant emojis for headings to match the lively Market Research Document theme.
4. For each quadrant, use bullet points with bold sub-headers (e.g., `- **Strong Market Growth:** ...`).
    - *CRITICAL*: For the **Opportunities** quadrant, explicitly highlight specific competitor flaws or user pain points provided in the context (labeled as "Competitor Weakness") as actionable gaps in the market that the new product can solve.
5. Create a `## 🔄 TOWS Strategic Matrix` section containing the raw TOWS matrix mapped strategies extracted from context.
6. Include a `## 🎯 Strategic Recommendations` section at the end, synthesizing the final `strategic_verdict` to conclude the document.
7. The styling should match a premium business report. Use blockquotes (`>`) for key insights.

Generate the full markdown document below:
"""

swot_prompt_template = ChatPromptTemplate.from_template(SWOT_GENERATION_PROMPT)


# -----------------------------------------------------------------------------
# COMPETITIVE GAP ANALYZER PROMPT
# -----------------------------------------------------------------------------
GAP_ANALYZER_PROMPT = """
You are a brilliant Product Strategist performing a Competitive Gap Analysis.
Your goal is to cross-reference customer complaints about competitors against a new proposed business idea to identify structural "Hard Strengths" and "Opportunities".

NEW BUSINESS IDEA:
{idea_name}
(Description/Context: {idea_description})

COMPETITOR REVIEWS (Raw User Complaints):
{reviews_json}

INSTRUCTIONS (Chain of Thought):
1. Think step-by-step about what the core complaints actually mean. What exactly are these competitors failing to do?
2. Compare each identified failure against the inherent nature of the New Business Idea.
3. If the New Business Idea inherently solves the competitor's failure by default (e.g. they complain about complexity, but the new idea is an "Automated AI Bot"), classify that specific gap as a "Hard Strength" for the new idea.
4. If it's a gap the new idea could potentially fill but isn't explicitly defined as doing so yet, classify it as an "Opportunity".

RETURN ONLY STRICT JSON in the following format (NO MARKDOWN WRAPPERS):
{{
    "hard_strengths": [
        "Strength 1: Because competitors suffer from X, our inherent feature Y acts as a structural advantage."
    ],
    "opportunities": [
        "Opportunity 1: Competitors fail at Z. We have an opportunity to capture their dissatisfied users by building Z."
    ]
}}
"""


# -----------------------------------------------------------------------------
# REGULATORY AND BARRIER EXTRACTION PROMPT
# -----------------------------------------------------------------------------
BARRIER_EXTRACTION_PROMPT = """
You are a globally recognized Compliance and Economic Strategy Consultant conducting a PEST Analysis (Political, Economic, Social, Technological) focus on regulatory and barrier threats.
Your goal is to analyze raw search results about a specific region and business idea to identify serious external threats.

BUSINESS IDEA / INDUSTRY: {idea_name}
TARGET REGION: {region}

RAW SEARCH SNIPPETS (Legal/Economic/Compliance limitations):
{search_snippets}

INSTRUCTIONS:
1. Review the provided search snippets.
2. Identify any explicit or highly probable regulatory laws, compliance bottlenecks, economic barriers (e.g., high licensing fees, GPU costs, taxation), or data/privacy regulations affecting this industry in this region.
3. Summarize the top 3-5 most critical threats realistically facing this business.
4. If no significant barriers are found, state that the regulatory landscape currently appears favorable, or list general tech startup barriers.

RETURN ONLY STRICT JSON in the following format (NO MARKDOWN WRAPPERS):
{{
    "regulatory_and_economic_threats": [
        "Threat 1: Explicit description of the legal or economic barrier found."
    ]
}}
"""

# -----------------------------------------------------------------------------
# TOWS MATRIX SYNTHESIS PROMPT (The Reducer)
# -----------------------------------------------------------------------------
TOWS_SYNTHESIS_PROMPT = """
You are a master Strategic Consultant tasked with building a TOWS Matrix (Threats, Opportunities, Weaknesses, Strengths).
Your goal is to synthesize the disparate data points from market research into actionable, cross-quadrant strategies and provide a final Go/No-Go verdict.

BUSINESS IDEA: {idea_name}
Top-Level Pain Score: {pain_score}
Top-Level Market Growth (CAGR): {cagr}

EXTRACTED STRENGTHS (Internal):
{strengths}

EXTRACTED WEAKNESSES (Internal):
{weaknesses}

EXTRACTED OPPORTUNITIES (External):
{opportunities}

EXTRACTED THREATS (External / PEST):
{threats}

INSTRUCTIONS:
1. Review all the data provided.
2. Develop 1-2 powerful strategies for each TOWS quadrant:
   - SO (Maxi-Maxi): How to use Strengths to maximize Opportunities.
   - ST (Maxi-Mini): How to use Strengths to minimize Threats.
   - WO (Mini-Maxi): How to minimize Weaknesses by taking advantage of Opportunities.
   - WT (Mini-Mini): How to minimize Weaknesses and avoid Threats (defensive strategy).
3. Synthesize everything into a final `strategic_verdict`. Address whether the product is recommended to proceed, requires a pivot, or is too risky. If Pain Score is < 50 or Market is highly negative, advise caution or pivot.

RETURN ONLY STRICT JSON in the following format (NO MARKDOWN WRAPPERS):
{{
    "tows_matrix": {{
        "SO_Strategies": ["Strategy 1", "Strategy 2"],
        "ST_Strategies": ["Strategy 1"],
        "WO_Strategies": ["Strategy 1"],
        "WT_Strategies": ["Strategy 1"]
    }},
    "strategic_verdict": "Comprehensive paragraph detailing the final strategic recommendation."
}}
"""
