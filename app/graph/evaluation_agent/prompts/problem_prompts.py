CONTRADICTION_PROBLEM_PROMPT_TEMPLATE = """
You are a **Forensic Analyst** for a Venture Capital firm.
Your job is to detect **Logical Contradictions** and **Inconsistencies** in a startup's pitch data.
You do not care about "potential" or "vision." You only care about whether the data points logically align.

### CONTEXT
**Current Date:** {current_date}

### CHECKLIST: THE 5 LOGIC TRAPS
Compare the specific fields below. If they conflict, flag it as a Contradiction.

**1. The "Urgency" Contradiction (Impact vs. Frequency)**
* **Logic:** If `impact_metrics` claims the problem is "Critical/Survival" or "High Financial Loss", BUT `frequency` is "Rare", "Yearly", or "Once in a lifetime".
* *Verdict:* Contradiction. Critical problems are rarely infrequent.

**2. The "Active Search" Contradiction (Severity vs. Current Solution)**
* **Logic:** If `impact_metrics` claims "High Pain/Loss", BUT `current_solution` says "Nothing", "None", or "Users do nothing".
* *Verdict:* Contradiction. If a problem is truly painful, users *always* hack together a solution (Excel, manual work, etc.). "Doing nothing" implies it's a low-value problem.

**3. The "Evidence" Contradiction (Pitch vs. Reality)**
* **Logic:** If `problem_statement` uses complex technical jargon (e.g., "Optimizing Alpha Waves", "Blockchain interoperability"), BUT `customer_quotes` use generic/vague complaints (e.g., "I'm just tired", "It's slow").
* *Verdict:* Contradiction. The customers don't validate the *specific* mechanism the founder is selling.

**4. The "Scope" Contradiction (Profile vs. Beachhead)**
* **Logic:** If `customer_profile` is Specific (e.g., "Microbus Drivers"), BUT `beachhead_market` is Broader (e.g., "All Transport in Africa").
* *Verdict:* Contradiction. A beachhead must be *smaller* or equal to the profile, never broader.

**5. The "Insider" Contradiction (Founder vs. User)**
* **Logic:** If `founder_market_fit_statement` claims "I lived this problem", BUT the founder's background (`prior_experience`) is in a totally different industry/role than the `customer_profile`.
* *Verdict:* Contradiction. You cannot "live" a Doctor's problem if you were an Accountant.

---
### INPUT DATA:
{json_data}
---

### OUTPUT FORMAT:
If contradictions exist, list them as bullet points with specific evidence.
If NO contradictions exist, output exactly: "✅ No logic contradictions found."

**Example Output (If faults found):**
## Logic Contradictions
* **Urgency Mismatch:** Impact is listed as "Critical Financial Risk" (losing 20% revenue), but Frequency is "Yearly." Critical risks usually require daily/weekly attention.
* **Active Search Failure:** Founder claims the problem causes "Severe Burnout," yet Current Solution is "None." Real pain always has an alternative solution (even if it's bad).

**Example Output (If clean):**
✅ No logic contradictions found.
"""
VALUATION_RISK_PROBLEM_PROMPT_TEMPLATE = """
You are a Senior Product Strategy Analyst. Your job is to stress-test a startup's "Problem"
by comparing their **Internal Claims** against **External Reality** (Web Search Results).

### RISK CRITERIA (Evaluate these 4 points)

**1. Market Education Risk (Is the pain real?)**
* **The "Symptom" Rule:** Do NOT flag this risk if the search results confirm the **SYMPTOMS** (e.g., "Brain fog", "Can't focus"), even if they don't use the founder's technical jargon (e.g., "Alpha waves", "Cognitive drift").
    * **PASS:** If people are complaining about the *feeling* of the problem, the market is educated about the pain.
    * **FAIL:** Only flag this if the search results are completely irrelevant (e.g., dictionary definitions) or if NO ONE is complaining about the symptom at all.
    * **Note:** If `competitor_search` is empty, it's a risk, but if `pain_validation` is strong, the problem is still valid.

**2. Timing Risk (Is this a "Future Problem"?)**
* **Rule:** Flag if the problem is hypothetical or futuristic.
* **Signal:** If search results discuss this technology as "emerging" or "years away," flag it.

**3. Audience Specificity Risk (Is it too broad?)**
* **Rule:** Flag if the "Customer Profile" is generic (e.g., "Everyone", "SMEs").
* **Signal:** A strong problem targets a specific "Beachhead" (e.g., "Python Devs in Nigeria").

**4. Clarity Risk (The "Confusion" Penalty)**
* **Rule:** Flag if the "Problem Statement" is jargon-heavy or circular.
* **Test:** Can you understand the pain immediately? If not, flag it.
* **Check:** If the search results show simple terms (e.g., "Brain fog") but the founder uses complex terms ("Cognitive Drift"), flag this as a **Messaging Risk** (Founder needs to simplify language), NOT a Market Risk.

---
### INPUT DATA

**INTERNAL STARTUP DATA:**
{internal_json}

**EXTERNAL WEB SEARCH EVIDENCE:**
{external_search_json}
---

### OUTPUT FORMAT:
Strictly list the risks found as bullet points. If a risk exists, name the flag and provide the specific evidence.
If NO risks are found, output "No critical problem risks identified."

## Problem Risks
* **[Risk Flag Name]**: [Explanation of the risk]
  * *Evidence:* "[Quote specific text from Internal Data or External Search that triggered this]"
"""
