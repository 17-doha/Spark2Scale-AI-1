from pydantic import BaseModel, Field
from typing import List

# ─── Cheat Sheet Schemas (used by the extractor pipeline) ─────────────────────

class HardNumbers(BaseModel):
    burn_rate: str = Field(description="Monthly burn rate, e.g., '$100/mo'")
    target_raise: str = Field(description="Target amount of money they are trying to raise")

class EvaluationPillars(BaseModel):
    team: str = Field(description="1-sentence summary of team strength or weakness")
    problem: str = Field(description="1-sentence summary of the problem definition")
    product: str = Field(description="1-sentence summary of the product/solution")
    gtm: str = Field(description="1-sentence summary of go-to-market strategy")
    traction: str = Field(description="1-sentence summary of current traction")
    vision: str = Field(description="1-sentence summary of the vision")
    business: str = Field(description="1-sentence summary of the business model/economics")
    market: str = Field(description="1-sentence summary of market analysis")
    operations: str = Field(description="1-sentence summary of operations/runway")

class SWOTAnalysis(BaseModel):
    strengths: List[str]
    weaknesses: List[str]
    opportunities: List[str]
    threats: List[str]

class VCCheatSheet(BaseModel):
    startup_name: str = Field(description="The name of the startup")
    evaluation_pillars: EvaluationPillars
    business_plan_context: str = Field(description="1-2 sentences summarizing the core business plan.")
    cap_table_context: str = Field(description="Summary of equity distribution and any cap table red flags.")
    market_research_stats: str = Field(description="Key market size values (TAM/SAM/SOM) and growth trends.")
    expected_ppt_flow: List[str] = Field(description="Chronological list of topics expected in their pitch.")
    prior_recommendations: List[str] = Field(description="Key recommendations previously given to the founder.")
    swot_analysis: SWOTAnalysis
    hard_numbers: HardNumbers
    vulnerabilities_to_attack: List[str] = Field(description="Top 2-3 critical flaws to challenge the founder on")
    diligence_questions: List[str] = Field(description="Exactly 3 specific diligence questions for investors to ask.")


# ─── Grammar & Review Schemas (used by the agent at runtime) ──────────────────

class GrammarIssue(BaseModel):
    """A single grammar / filler / weak-phrasing incident captured silently during the pitch."""
    timestamp: float = Field(description="Session-elapsed seconds when the issue occurred.")
    text_fragment: str = Field(description="The exact phrase or sentence that contained the issue.")
    issues: List[str] = Field(description="List of specific problems, e.g. ['filler: um', 'grammar: subject-verb agreement']")


class PostPitchReview(BaseModel):
    """
    The structured review delivered by Sparky at the end of the evaluating phase.
    Built from session_log + grammar_buffer accumulated during the session.
    """
    filler_words: List[str] = Field(description="List of filler words detected (um, uh, like, you know, etc.)")
    weak_phrases: List[str] = Field(description="Vague or weak investment phrases flagged (e.g. 'basically', 'kind of')")
    grammar_issues: List[GrammarIssue] = Field(description="Specific grammar moments flagged during the pitch.")
    interrupts_triggered: int = Field(description="Total number of live interrupts Sparky made (inconsistency, contradiction, nervousness).")
    strengths: List[str] = Field(description="What the founder did well in this pitch session.")
    next_steps: List[str] = Field(description="Top 3 concrete actions for the founder to improve before next pitch.")