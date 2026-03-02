from .helpers import calculate_trigger_strength

MULTIPLIERS = {"high": 1.5, "medium": 1.3, "low": 1.1}

PATTERN_LIBRARY = {
          # --- Team CATEGORY
          "FP-TEAM-001": {
              "name": "Founder Avoids the Hard Job", "severity": "high",
              "triggers": lambda s: s['gtm']['score'] <= 2 or "not selling" in s['team']['description'].lower(),
              "template": "Founder personally owns the next critical execution loop (sales, hiring, customer interviews) for 30-60 days. Avoid delegating core learning."
          },
          "FP-TEAM-002": {
              "name": "Critical Skill Gap Ignored", "severity": "high",
              "triggers": lambda s: "missing capability" in s['team']['description'].lower() or "repeated delays" in s['ops']['description'].lower(),
              "template": "Identify the single missing capability and close it via co-founder, advisor, or targeted hire. Avoid generalist hires."
          },
          "FP-TEAM-003": {
              "name": "Solo Founder Overload", "severity": "medium",
              "triggers": lambda s: "solo founder" in s['team']['description'].lower() and s['ops']['score'] <= 3,
              "template": "Add a complementary partner or reduce scope aggressively. Avoid hero-mode scaling."
          },
          "FP-TEAM-004": {
              "name": "Founder Conflict Avoidance", "severity": "high",
              "triggers": lambda s: "tension" in s['team']['description'].lower() or "decision stalls" in s['ops']['description'].lower(),
              "template": "Force explicit role ownership and decision rights. Avoid passive alignment."
          },
          "FP-TEAM-005": {
              "name": "Burnout Masked as Strategy", "severity": "medium",
              "triggers": lambda s: "withdrawal" in s['team']['description'].lower() or "vague progress" in s['ops']['description'].lower(),
              "template": "Reset operating cadence and reduce goals. Avoid adding strategic initiatives."
          },
          # --- Problem CATEGORY
          "FP-PROBLEM-001": {
              "name": "Nice-to-Have Problem", "severity": "high",
              "triggers": lambda s: s['problem']['score'] <= 2 or "weak conversion" in s['traction']['description'].lower(),
              "template": "Validate willingness to pay with 10 buyers. Avoid feature expansion."
          },
          "FP-PROBLEM-002": {
              "name": "Symptom-Level Solution", "severity": "medium",
              "triggers": lambda s: "churn" in s['traction']['description'].lower() and "surface pain" in s['problem']['description'].lower(),
              "template": "Rerun discovery to isolate root cause. Avoid incremental fixes."
          },
          "FP-PROBLEM-003": {
              "name": "Buyer/User Confusion", "severity": "medium",
              "triggers": lambda s: "long sales cycles" in s['gtm']['description'].lower() or "pricing friction" in s['economics']['description'].lower(),
              "template": "Explicitly define buyer vs user and rebuild GTM around buyer. Avoid broad targeting."
          },
          "FP-PROBLEM-004": {
              "name": "Abstract Problem Framing", "severity": "low",
              "triggers": lambda s: "vague customer language" in s['problem']['description'].lower() or "conceptual" in s['problem']['description'].lower(),
              "template": "Anchor problem in a single repeatable scenario. Avoid generic narratives."
          },
          "FP-PROBLEM-005": {
              "name": "Market Timing Misread", "severity": "high",
              "triggers": lambda s: "slow adoption" in s['traction']['description'].lower() and s['problem']['score'] >= 4,
              "template": "Narrow to early adopters or pause scaling. Avoid waiting on market education."
          },

          # --- Product CATEGORY
          "FP-PRODUCT-001": {
              "name": "No Core Use Case", "severity": "medium",
              "triggers": lambda s: s['product']['score'] <= 2 and "unused" in s['product']['description'].lower(),
              "template": "Choose one use case and optimize for daily/weekly value. Avoid roadmap sprawl."
          },
          "FP-PRODUCT-002": {
              "name": "Feature Accumulation Without Usage", "severity": "high",
              "triggers": lambda s: "low retention" in s['traction']['description'].lower() and "high shipping velocity" in s['ops']['description'].lower(),
              "template": "Freeze new features; instrument and fix core flow. Avoid pivots."
          },
          "FP-PRODUCT-003": {
              "name": "Demo-Driven Validation", "severity": "medium",
              "triggers": lambda s: "strong demos" in s['gtm']['description'].lower() and s['traction']['score'] <= 2,
              "template": "Measure post-demo usage and outcomes. Avoid demo optimization."
          },
          "FP-PRODUCT-004": {
              "name": "Building Before Learning", "severity": "high",
              "triggers": lambda s: "assumptions untested" in s['product']['description'].lower() or "engineering-led" in s['product']['description'].lower(),
              "template": "Validate hypotheses before building. Avoid backlog growth."
          },
          "FP-PRODUCT-005": {
              "name": "No Instrumentation", "severity": "medium",
              "triggers": lambda s: "unknown user behavior" in s['product']['description'].lower() or "blind execution" in s['product']['description'].lower(),
              "template": "Implement basic usage tracking before shipping more. Avoid vanity metrics."
          },

          # --- Market CATEGORY
          "FP-MARKET-001": {
              "name": "Overstated TAM", "severity": "low",
              "triggers": lambda s: "unclear icp" in s['market']['description'].lower() or "vague customer" in s['market']['description'].lower(),
              "template": "Narrow ICP to a single buyer profile. Avoid TAM storytelling."
          },
          "FP-MARKET-002": {
              "name": "Fragmented Customer Base", "severity": "medium",
              "triggers": lambda s: "high variance" in s['market']['description'].lower() or "bespoke" in s['product']['description'].lower(),
              "template": "Focus on one homogeneous segment. Avoid bespoke solutions."
          },
          "FP-MARKET-003": {
              "name": "Competitive Naivety", "severity": "low",
              "triggers": lambda s: "no competitors" in s['market']['description'].lower() or "ignoring substitutes" in s['market']['description'].lower(),
              "template": "Map real alternatives customers use. Avoid dismissiveness."
          },
          "FP-MARKET-004": {
              "name": "Local Maximum Market", "severity": "medium",
              "triggers": lambda s: "growth stalls" in s['traction']['description'].lower() and s['market']['score'] >= 4,
              "template": "Validate expansion paths early. Avoid premature scaling."
          },
          "FP-MARKET-005": {
              "name": "Regulatory Blindness", "severity": "high",
              "triggers": lambda s: "procurement cycles" in s['gtm']['description'].lower() or "ignored constraints" in s['market']['description'].lower(),
              "template": "Adjust ICP or GTM to regulatory reality. Avoid hoping it speeds up."
          },

          # --- Traction CATEGORY
          "FP-TRACTION-001": {
              "name": "Vanity Metrics", "severity": "low",
              "triggers": lambda s: "signups" in s['traction']['description'].lower() and s['traction']['score'] <= 2,
              "template": "Shift to retention and repeat usage. Avoid top-of-funnel obsession."
          },
          "FP-TRACTION-002": {
              "name": "Growth Without Understanding", "severity": "medium",
              "triggers": lambda s: "can't explain growth" in s['traction']['description'].lower() or "accidental traction" in s['traction']['description'].lower(),
              "template": "Isolate and replicate growth drivers. Avoid new experiments."
          },
          "FP-TRACTION-003": {
              "name": "Churn Hidden by Growth", "severity": "high",
              "triggers": lambda s: s['traction']['score'] <= 2 and ("low retention" in s['traction']['description'].lower() or "active weekly users" in s['traction']['description'].lower()),
              "template": "Fix churn before scaling. Avoid paid growth."
          },
          "FP-TRACTION-004": {
              "name": "Inconsistent Signals", "severity": "low",
              "triggers": lambda s: "spiky metrics" in s['traction']['description'].lower() or "non-repeatable" in s['traction']['description'].lower(),
              "template": "Standardize acquisition motion. Avoid channel hopping."
          },
          "FP-TRACTION-005": {
              "name": "No Learning Velocity", "severity": "medium",
              "triggers": lambda s: "metrics unchanged behavior" in s['traction']['description'].lower() or "data without decisions" in s['traction']['description'].lower(),
              "template": "Tie metrics to weekly decisions. Avoid dashboards for show."
          },

          # --- GTM CATEGORY
          "FP-GTM-001": {
              "name": "Founder Not Selling", "severity": "high",
              "triggers": lambda s: "early sales hires" in s['gtm']['description'].lower() or "delegated learning" in s['gtm']['description'].lower(),
              "template": "Founder-led sales until repeatable. Avoid outsourcing insight."
          },
          "FP-GTM-002": {
              "name": "Too Many Channels", "severity": "medium",
              "triggers": lambda s: s['gtm']['score'] <= 2 and "multiple channels" in s['gtm']['description'].lower(),
              "template": "Double down on one channel. Avoid parallel testing."
          },
          "FP-GTM-003": {
              "name": "Premature Scaling", "severity": "high",
              "triggers": lambda s: "sales hires without playbook" in s['gtm']['description'].lower() or "scale before signal" in s['gtm']['description'].lower(),
              "template": "Prove repeatability first. Avoid headcount growth."
          },
          "FP-GTM-004": {
              "name": "Sales Motion Mismatch", "severity": "medium",
              "triggers": lambda s: "long cycles" in s['gtm']['description'].lower() and "low deal size" in s['gtm']['description'].lower(),
              "template": "Align motion with pricing. Avoid forcing fit."
          },
          "FP-GTM-005": {
              "name": "Pricing Avoidance", "severity": "medium",
              "triggers": lambda s: "pricing not tested" in s['economics']['description'].lower() or "fear-based pricing" in s['gtm']['description'].lower(),
              "template": "Test higher pricing with real buyers. Avoid discounts."
          },

          # --- Economics CATEGORY
          "FP-ECON-001": {
              "name": "Burn Without Milestones", "severity": "high",
              "triggers": lambda s: "runway decline" in s['economics']['description'].lower() or s['economics']['score'] <= 2,
              "template": "Tie spend to explicit milestones. Avoid vague goals."
          },
          "FP-ECON-002": {
              "name": "Underpricing Early", "severity": "medium",
              "triggers": lambda s: "low arpu" in s['economics']['description'].lower() or "buying traction" in s['economics']['description'].lower(),
              "template": "Raise prices to signal value. Avoid free tiers."
          },
          "FP-ECON-003": {
              "name": "Gross Margin Blindness", "severity": "high",
              "triggers": lambda s: "unknown margins" in s['economics']['description'].lower() or "ignoring unit economics" in s['economics']['description'].lower(),
              "template": "Model margins now. Avoid 'fix later' thinking."
          },
          "FP-ECON-004": {
              "name": "Fundraising as Strategy", "severity": "medium",
              "triggers": lambda s: "pitch-first" in s['economics']['description'].lower() or "capital over progress" in s['economics']['description'].lower(),
              "template": "Delay fundraising until proof points. Avoid deck iteration."
          },
          "FP-ECON-005": {
              "name": "Runway Delusion", "severity": "high",
              "triggers": lambda s: "optimistic forecasts" in s['economics']['description'].lower() or "overestimated time" in s['economics']['description'].lower(),
              "template": "Plan for downside runway. Avoid best-case planning."
          },

          # --- Vision CATEGORY
          "FP-VISION-001": {
              "name": "Vision Outruns Execution", "severity": "medium",
              "triggers": lambda s: s['vision']['score'] >= 4 and s['traction']['score'] <= 2,
              "template": "Translate vision into 90-day goals. Avoid long-term reframes."
          },
          "FP-VISION-002": {
              "name": "Category Creation Too Early", "severity": "low",
              "triggers": lambda s: "buyer confusion" in s['vision']['description'].lower() or "market education burden" in s['vision']['description'].lower(),
              "template": "Win a niche before category claims. Avoid thought leadership."
          },
          "FP-VISION-003": {
              "name": "Vision Thrash", "severity": "medium",
              "triggers": lambda s: "constant narrative change" in s['vision']['description'].lower() or "strategy shifts" in s['vision']['description'].lower(),
              "template": "Lock direction for 6 months. Avoid reactive pivots."
          },
          "FP-VISION-004": {
              "name": "Founder Identity Locked to Vision", "severity": "high",
              "triggers": lambda s: "defensive feedback" in s['vision']['description'].lower() or "ego-protected" in s['vision']['description'].lower(),
              "template": "Separate self-worth from hypotheses. Avoid argumentation."
          },
          "FP-VISION-005": {
              "name": "Short-Term Neglect", "severity": "high",
              "triggers": lambda s: "missed execution" in s['vision']['description'].lower() or "ignoring near-term" in s['vision']['description'].lower(),
              "template": "Re-anchor on next 30-60 days. Avoid distant planning."
          },

          # --- Operations CATEGORY
          "FP-OPS-001": {
              "name": "No Operating Cadence", "severity": "medium",
              "triggers": lambda s: "no weekly planning" in s['ops']['description'].lower() or "reactive execution" in s['ops']['description'].lower(),
              "template": "Establish weekly goals and reviews. Avoid tool churn."
          },
          "FP-OPS-002": {
              "name": "Decision Bottlenecks", "severity": "medium",
              "triggers": lambda s: "founder approval everywhere" in s['ops']['description'].lower() or "centralized control" in s['ops']['description'].lower(),
              "template": "Delegate clear ownership. Avoid consensus paralysis."
          },
          "FP-OPS-003": {
              "name": "Hiring Timing Errors", "severity": "medium",
              "triggers": lambda s: "burn spikes" in s['economics']['description'].lower() or "panic hiring" in s['ops']['description'].lower(),
              "template": "Hire against milestones, not hope. Avoid panic hiring."
          },
          "FP-OPS-004": {
              "name": "Ownership Ambiguity", "severity": "medium",
              "triggers": lambda s: "tasks slip" in s['ops']['description'].lower() or "everyone responsible" in s['ops']['description'].lower(),
              "template": "Assign single owners per initiative. Avoid shared accountability."
          },
          "FP-OPS-005": {
              "name": "Process Aversion", "severity": "low",
              "triggers": lambda s: "repeated mistakes" in s['ops']['description'].lower() or "chaos disguised as agility" in s['ops']['description'].lower(),
              "template": "Add minimal process where pain exists. Avoid dogma."
          }
          }

def detect_patterns(scores):
    matched = []
    
    # Track which categories have patterns firing at medium or high severity
    category_firings = {}
    
    for p_id, p_info in PATTERN_LIBRARY.items():
        if p_info["triggers"](scores):
            # Extract category from p_id (e.g. "FP-TEAM-001" -> "TEAM")
            category = p_id.split("-")[1]
            if p_info["severity"] in ["medium", "high"]:
                category_firings[category] = category_firings.get(category, 0) + 1
            
            # Temporary store
            matched.append({
                "pattern_id": p_id,
                "name": p_info["name"],
                "severity": p_info["severity"],
                "template": p_info["template"],
                "category": category
            })
            
    # Now calculate confidence and strength with full context
    final_matched = []
    for match in matched:
        p_id = match["pattern_id"]
        severity = match["severity"]
        category = match["category"]
        
        # Cross-category convergence logic
        other_categories_firing = sum(1 for c, count in category_firings.items() if c != category and count > 0)
        same_category_firings = category_firings.get(category, 0)
        
        # Confidence calculation
        if other_categories_firing >= 2:
            confidence = "HIGH"
            reason = f"Supported by {other_categories_firing} other independent risk categories"
            cross_category_support = True
        elif severity == "high" or same_category_firings >= 2:
            confidence = "MEDIUM"
            if severity == "high":
                 reason = "High severity core pattern"
            else:
                 reason = f"Supported by {same_category_firings - 1} other patterns in same category"
            cross_category_support = False
        else:
            confidence = "LOW"
            reason = "Isolated signal without cross-category support"
            cross_category_support = False
            
        strength = calculate_trigger_strength(severity, MULTIPLIERS, cross_category_support=cross_category_support)
        label = "strong" if strength > 1.0 else "moderate" if strength >= 0.5 else "weak"
        
        final_matched.append({
            "pattern_id": p_id,
            "name": match["name"],
            "severity": severity,
            "strength_score": strength,
            "strength_label": label,
            "template": match["template"],
            "confidence": confidence,
            "confidence_reasoning": reason
        })
        
    return sorted(final_matched, key=lambda x: x["strength_score"], reverse=True)