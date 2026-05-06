def generate_validation_queries_prompt(idea, problem_statement, region="Global"):
    # IMPORTANT: The JSON example block uses angle-bracket placeholders (<...>)
    # instead of embedding idea/problem_statement directly inside the JSON example.
    # This avoids a subtle bug: if idea or problem_statement themselves contain
    # curly braces, the f-string would raise a KeyError at runtime.
    # The LLM receives the real values from the top block and is instructed to
    # generate concrete queries -- not to copy the placeholder text literally.
    return f"""
    Idea: {idea}
    Problem: {problem_statement}
    Region: {region}

    Generate search queries to validate this problem EXISTS and people are ACTIVELY seeking solutions.
    Tailor queries to the region where relevant (e.g. include region name for local markets).

    RETURN JSON with TWO categories (generate real queries based on the Idea and Problem above):
    {{
        "problem_queries": [
            "site:reddit.com <specific problem keywords>",
            "site:twitter.com frustrated with <specific problem keywords>",
            "site:quora.com need help with <specific problem keywords>"
        ],
        "solution_queries": [
            "site:producthunt.com <idea category> alternatives",
            "site:g2.com <idea category> reviews",
            "site:trustpilot.com similar to <idea category>"
        ]
    }}

    Make queries specific and focused on REAL USER PAIN and EXISTING SOLUTIONS.
    Replace all <...> placeholders with real terms derived from the Idea and Problem above.
    """


def analyze_pain_points_prompt(idea, problem_statement, evidence, region="Global"):
    formatted_evidence = evidence
    if isinstance(evidence, list):
        formatted_evidence = "\n".join([str(e) for e in evidence])

    return f"""
    You are a rigorous market validation analyst. Be REALISTIC and EVIDENCE-BASED.

    HYPOTHESIS: '{idea}' solves '{problem_statement}'.
    TARGET REGION: {region}

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
       - Is the pain present specifically in the target region ({region})?

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