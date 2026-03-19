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
Return ONLY STRICT JSON in the following format (NO MARKDOWN WRAPPERS):
{{
    "idea_name": "...",
    "title": "SWOT Analysis: [Idea Name]",
    "introduction": "Brief introduction paragraph explaining the strategic position of the product/service.",
    "strengths": [
        "**Header:** description..."
    ],
    "weaknesses": [
        "Weakness statement (Severity: X/10)"
    ],
    "opportunities": [
        "**Gap identified:** description..."
    ],
    "threats": [
        "**Threat:** description..."
    ],
    "tows_matrix_raw_strategies": [
        "Strategy 1...", "Strategy 2..."
    ],
    "strategic_recommendations": "Crucial synthesis of the final strategic verdict."
}}

CRITICAL INSTRUCTIONS:
- For Opportunities, explicitly highlight specific competitor flaws or user pain points provided in the context as actionable gaps.
- For Weaknesses, each bullet must include the severity score in parentheses. DO NOT add, invent, or infer any weaknesses not present in the provided context.
- Embed the raw TOWS matrix mapped strategies extracted from context directly into the `tows_matrix_raw_strategies` array.
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

STRICT DEFINITIONS — read carefully before classifying:
- HARD STRENGTH: An INTERNAL capability, feature, or architectural advantage that the new product inherently possesses by design. It must describe something the product *IS* or *DOES*, not something a competitor *FAILS* at. Example: "Our app is fully automated" is a strength. "Competitors are manual" is NOT a strength — it's an opportunity.
- OPPORTUNITY: An EXTERNAL market condition, unmet user need, or competitor failure that the new product could exploit. It describes what exists *outside* the product in the market.

INSTRUCTIONS (Chain of Thought):
1. Group all competitor complaints by their underlying theme (e.g. pricing, usability, missing features, poor support). Do not treat each individual complaint as a separate item — merge complaints that point to the same root issue.
2. For each distinct theme (max 5 themes total):
   a. Ask: does the new idea inherently solve this by its core design? → Hard Strength (describe what the product does, not what competitors fail at)
   b. Ask: is this a gap the new idea *could* fill but isn't explicitly built to yet? → Opportunity (describe the external market gap and the user need)
   c. A theme cannot appear in BOTH lists. Pick the most accurate classification.
3. Cap output at 3-4 hard_strengths and 4-5 opportunities. If you have more, merge the weakest/most similar ones.
4. Each item must be a unique insight — no two items should convey the same meaning even if worded differently.

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
# WEAKNESS ANALYSIS PROMPT
# -----------------------------------------------------------------------------
WEAKNESS_ANALYSIS_PROMPT = """
You are a rigorous Business Analyst performing a Weakness Identification exercise for a SWOT Analysis.
Your task is to produce ONLY real, evidence-backed weaknesses — NO speculation, NO generic filler.

BUSINESS IDEA: {idea_name}
Description: {idea_description}

---
SECTION A — SCRAPED WEB SIGNALS (real user complaints and market observations):
{scraped_signals}

---
SECTION B — BUSINESS METRICS (from market research report, with threshold evaluations):
{business_metrics}

---
INSTRUCTIONS (think step by step):

1. Go through each item in SECTION A. For each snippet:
   - Ask: does this reveal a real weakness in the PRODUCT CATEGORY, MARKET DYNAMICS, or BUSINESS MODEL that would affect a new entrant in this space?
   - If yes, extract it as a weakness with source type = "SCRAPE_BACKED"
   - Ignore snippets that are about specific competitors (those belong in Opportunities), irrelevant topics, or purely positive content

2. Go through each metric in SECTION B. For each metric:
   - If its threshold_label is anything other than HEALTHY/ACCEPTABLE/LOW_RISK/HIGH/MANAGEABLE, it signals a weakness
   - Write a clear business statement explaining WHY this metric value is problematic for this specific idea
   - Source type = "METRIC_BACKED"

3. De-duplicate aggressively. If two weaknesses share the same 
   root cause, merge them into one entry and take the higher 
   severity score. No two items in the final output should 
   convey the same underlying business risk.

   
4. Assign a severity score 1-10:
   - 8-10: Critical — could kill the business or block market entry
   - 5-7: Significant — will require focused mitigation
   - 1-4: Minor — awareness-level, low immediate impact

5. DO NOT invent weaknesses. If there are no real weakness signals found, return an empty weaknesses array.

RETURN ONLY STRICT JSON — NO MARKDOWN WRAPPERS, NO PREAMBLE:
{{
    "weaknesses": [
        {{
            "statement": "Clear, specific weakness statement written for a business audience.",
            "source_type": "SCRAPE_BACKED | METRIC_BACKED | BOTH",
            "evidence": "Brief quote or metric value that proves this weakness.",
            "severity": 7
        }}
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

# -----------------------------------------------------------------------------
# COMPETITOR ANALYSIS PROMPTS
# -----------------------------------------------------------------------------
def classify_competitors_prompt(idea_description: str, comps_listing: str) -> str:
    return f"""You are a startup market analyst.

Our product:
{idea_description}

Here is a list of competitors:
{comps_listing}

Classify EACH competitor as exactly ONE of:
  - direct   (targets the same customer segment with the same core value proposition)
  - indirect (addresses a related need or a different customer segment)

Reply ONLY with a strictly valid JSON object mapping the competitor name to the classification.
Example format:
{{
   "Notion": "direct",
   "Coda": "indirect"
}}
"""

def enrich_market_intelligence_prompt(batched_evidence_text: str) -> str:
    return f"""You are a senior competitive intelligence analyst writing a startup competitor analysis.

## Raw Evidence for Multiple Competitors (web snippets — treat these as ground truth)
{batched_evidence_text}

## Task
Using ONLY the evidence above, extract the following three fields for EACH competitor presented in the evidence.
Do NOT use your training knowledge if it contradicts the evidence. If the evidence is insufficient, write "Not enough data".

Reply ONLY with a STRICT JSON object mapping the competitor name to their fields. Example format:
{{
  "Competitor A": {{
    "target_audience": "<1–2 sentences: who they explicitly sell to>",
    "value_proposition": "<1 sentence: their core marketing promise or tagline>",
    "pricing_model": "<1–2 sentences: how they monetise>"
  }}
}}
"""

def enrich_product_reality_prompt(batched_evidence_text: str) -> str:
    return f"""You are a senior competitive intelligence analyst preparing a startup competitor analysis.

## Raw Evidence for Multiple Competitors (web snippets — treat these as ground truth)
{batched_evidence_text}

## Task
Using ONLY the evidence above, fill in the three fields below for EACH competitor presented in the evidence.
Be specific and concrete. Avoid vague marketing language.

Fields to extract:
- core_features: Describe actual technical capabilities (e.g. API accessibility, sync mechanisms, self-hosting). NOT a marketing feature list.
- strengths: Describe durable competitive advantages (moat) like deep ecosystem lock-in, dominant community, brand trust.
- weaknesses: Describe specific, concrete pain points from users (e.g. performance issues, missing features, poor mobile, confusing pricing).

CRITICAL: Each competitor's fields must be unique and based solely on 
their own evidence section. Do not copy or repeat content from one 
competitor to another, even if their evidence appears similar.

If the evidence does not support a field, write exactly: "Not enough data".

Reply ONLY with a STRICT JSON object mapping the competitor name to their fields. Example format:
{{
  "Competitor A": {{
    "core_features": "<2–4 sentences on most technically significant capabilities>",
    "strengths": "<2–3 sentences on durable moat>",
    "weaknesses": "<2–3 sentences on real documented gaps / complaints>"
  }}
}}
"""
