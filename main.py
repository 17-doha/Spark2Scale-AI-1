from fastapi import FastAPI
# from app.api.routes import workflow
import uvicorn


from app.core.logger import get_logger # Fixed import path

logger = get_logger("main")

def main():
    logger.info("Starting Spark2Scale AI API Server...")
    # reload=True is great for dev, implies 'main.py' is entry point
    uvicorn.run("app.api.main:app", host="0.0.0.0", port=8000, reload=True)

# app = FastAPI(title="Spark2Scale AI Agent")

# # # Include the workflow router
# # app.include_router(workflow.router, prefix="/api/v1", tags=["Workflow"])

# # @app.get("/")
# # def read_root():
# #     return {"message": "Spark2Scale AI Agent Service is Running"}

if __name__ == "__main__":
    main()

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

# from app.api.main import app
# import os
# from dotenv import load_dotenv
# from app.graph.recommendation_agent.workflow import run_recommendation_agent
# import json
# # 1. Load environment variables from .env file (override=True ensures .env takes precedence over system env vars)
# load_dotenv(override=True)

# # 2. Retrieve the API Key
# MY_API_KEY = os.getenv("GEMINI_API_KEY")

# # 3. Use the dictionaries from your notebook here
# # (I'm using placeholders; paste your actual dictionaries here)
# RAW_INPUT = {
#   "startup_evaluation": {
#     "meta_data": {
#       "form_type": "Pre-Seed & Seed Evaluation",
#       "last_updated": "2026-02-04"
#     },
#     "company_snapshot": {
#       "company_name": "Spark2Scale",
#       "website_url": "",
#       "hq_location": "Egypt",
#       "date_founded": "2025-07-01",
#       "current_stage": "Pre-seed",
#       "amount_raised_to_date": 0,
#       "current_round": {
#         "target_amount": 500,
#         "target_close_date": "2026-04-01"
#       }
#     },
#     "founder_and_team": {
#       "founders": [
#         {
#           "name": "Doha Hemdan",
#           "role": "CEO",
#           "ownership_percentage": 25,
#           "prior_experience": "AI Engineer at Tabaani",
#           "years_direct_experience": 1,
#           "founder_market_fit_statement": "Because we have done a real research and already knew different startup owners"
#         },
#         {
#           "name": "Salma Sherif",
#           "role": "CTO",
#           "ownership_percentage": 25,
#           "prior_experience": "AI Engineer at Praxilab",
#           "years_direct_experience": 1,
#           "founder_market_fit_statement": "Because we have done a real research and already knew different startup owners"
#         },
#         {
#           "name": "Mariam Elghandoor",
#           "role": "COO",
#           "ownership_percentage": 25,
#           "prior_experience": "ML Engineer",
#           "years_direct_experience": 1,
#           "founder_market_fit_statement": "Because we have done a real research and already knew different startup owners"
#         },
#         {
#           "name": "Sarah Elsayed",
#           "role": "CFO",
#           "ownership_percentage": 25,
#           "prior_experience": "Not specified",
#           "years_direct_experience": 1,
#           "founder_market_fit_statement": "Because we have done a real research and already knew different startup owners"
#         }
#       ],
#       "execution": {
#         "full_time_start_date": "2025-07-25",
#         "key_shipments": []
#       }
#     },
#     "problem_definition": {
#       "customer_profile": {
#         "role": "Early-stage founders",
#         "company_size": "2-50 people",
#         "industry": "Business / Tech Startups"
#       },
#       "problem_statement": "Early-stage founders lack a structured system to validate ideas, develop essential business documents, and reach investors.",
#       "current_solution": "Using ChatGPT and other LLMs depending on prompt engineering.",
#       "gap_analysis": "Current solutions are not specific enough to the startup evaluation sector.",
#       "frequency": "High (56% of startups fail in their first years).",
#       "impact_metrics": {
#         "cost_type": "Time, Money, and Risk",
#         "description": "Loss of capital and time due to lack of validation."
#       },
#       "evidence": {
#         "interviews_conducted": 12,
#         "customer_quotes": [
#           "market research"
#         ]
#       }
#     },
#     "product_and_solution": {
#       "product_stage": "MVP",
#       "demo_link": "",
#       "core_stickiness": "To evaluate ideas and reach investors.",
#       "differentiation": "Specialized in a specific sector and tailored solutions rather than general AI.",
#       "defensibility_moat": "The core technology implementation."
#     },
#     "market_and_scope": {
#       "beachhead_market": "Startup owners",
#       "market_size_estimate": "Not specified",
#       "long_term_vision": "Integrating mentors, evaluating larger startups, and adding validation for user inputs.",
#       "expansion_strategy": "Introduction of new products."
#     },
#     "traction_metrics": {
#       "stage_context": "Pre-Seed",
#       "user_count": 0,
#       "active_users_monthly": 0,
#       "partnerships_and_lois": [],
#       "early_revenue": "0"
#     },
#     "gtm_strategy": {
#       "buyer_persona": "Any team member",
#       "user_persona": "Founder",
#       "primary_acquisition_channel": "Word of mouth",
#       "sales_motion": "Founder-led sales",
#       "average_sales_cycle": "0 days",
#       "deal_closer": "None yet"
#     },
#     "business_model": {
#       "pricing_model": "Freemium",
#       "average_price_per_customer": 0,
#       "gross_margin": 0,
#       "monthly_burn": 100,
#       "runway_months": 0
#     },
#     "vision_and_strategy": {
#       "five_year_vision": "Become the primary startup evaluator in the MENA region.",
#       "category_definition": "Specialized AI",
#       "primary_risk": "Speed of execution and market entry.",
#       "use_of_funds": [
#         "Deployment",
#         "Model training",
#         "Acquiring customers"
#       ]
#     }
#   }
# }

# data = {
#   "team_report": {
#     "score": "2.5/5",
#     "explanation": "The team has some relevant experience in AI engineering, but there are gaps in execution capability and domain expertise. The founders' background is technically strong, but lacks demonstrable alignment with the problem statement and solution. Deducted 0.5 points for lack of domain expertise and 0.5 points for prior experience gaps in the specific domain of startup evaluation.",
#     "confidence_level": "Medium",
#     "red_flags": [
#       "Risk 1: Management & Execution Risk - Prior experience gaps in the specific domain of startup evaluation pose a risk to the team\u2019s ability to effectively validate ideas and execute the business plan.",
#       "Risk 2: Founder-Market Fit Alignment Risk - The founder\u2019s background, while technically strong, doesn\u2019t demonstrably align with the problem statement and solution, suggesting a lack of genuine understanding of the target market.",
#       "Risk 3: Problem Statement & Solution Risk - The problem statement and solution are vague and lack sufficient detail, failing to clearly articulate the core value proposition and potential impact.",
#       "Risk 4: Velocity Risk - The execution history shows a significant delay between initial concept and MVP development, indicating a potential risk of delayed market entry and missed opportunities."
#     ],
#     "green_flags": [
#       "Strength 1: The team has a strong technical background in AI engineering, with experience in AI engineering at Tabaani and Praxilab.",
#       "Strength 2: The founders have a clear understanding of the problem statement and solution, as evident from their fit statements."
#     ],
#     "score_numeric": 50
#   },
#   "problem_report": {
#     "score": "3.5/5",
#     "explanation": "The problem statement is clear, and the search evidence confirms the pain points of early-stage founders. However, the contradictions in the founder's alignment and scope mismatch between the customer profile and beachhead market raise concerns. The current solution, generic LLMs, does not directly address the need for better market research tools. -1 point due to 'Evidence' Contradiction. -1 point due to 'Scope' Contradiction. +1 point for 'High' frequency of the problem.",
#     "confidence_level": "Medium",
#     "red_flags": [
#       "Risk 1: Founder Alignment Mismatch - Founder's background in accounting is different from the customer profile.",
#       "Risk 2: Scope Mismatch - Customer Profile ('Microbus Drivers') is specific, while Beachhead Market ('All Transport in Africa') is broader.",
#       "Risk 3: Evidence Contradiction - Current solution (generic LLMs) does not directly address the need for better market research tools."
#     ],
#     "green_flags": [
#       "Strength 1: High frequency of the problem, with 56% of startups failing in early years due to lack of proper validation.",
#       "Strength 2: Search evidence confirms the pain points of early-stage founders, with multiple relevant results found."
#     ],
#     "score_numeric": 70
#   },
#   "product_report": {
#     "score": "0/5",
#     "explanation": "No clear solution or product provided. The startup's internal data is empty, and the forensic tool reports do not contain any relevant information. The 'Contradiction Check' found no logic contradictions, but this is not sufficient to award a score. The 'Risk & Competitor Check' did not identify any critical product risks, but this is also not enough to justify a score. The 'Tech Stack Analysis' and 'Visual Verification' reports are incomplete, and the 'Visual Verification' report does not contain a URL.",
#     "confidence_level": "Low",
#     "ocean_analysis": "Red Ocean - No direct competitors found, but the market is likely crowded due to the lack of information.",
#     "red_flags": [
#       "Flag 1: No clear solution or product provided.",
#       "Flag 2: Incomplete forensic tool reports."
#     ],
#     "green_flags": [],
#     "score_numeric": 0
#   },
#   "market_report": {
#     "score": "2/5",
#     "explanation": "The startup's beachhead is credible, but the expansion plan is unclear and the market is growing at a moderate rate. The 'David vs. Goliath' aspect is a significant risk, and the startup needs to demonstrate a unique value proposition to justify this early focus. The 'Teleportation' contradiction and 'Non-Sequitur' contradiction also highlight potential strategic vulnerabilities that require further investigation and refinement.",
#     "confidence_level": "Medium",
#     "market_sizing_check": "Valid - The TAM Report confirms the founder's claim of a growing market in the MENA region.",
#     "red_flags": [
#       "Flag 1: 'David vs. Goliath' aspect is a significant risk due to the presence of established tech giants like Google, Microsoft, and Amazon.",
#       "Flag 2: 'Teleportation' contradiction highlights a potential issue with the startup's location and beachhead market.",
#       "Flag 3: 'Non-Sequitur' contradiction indicates a lack of clear expansion dynamics and a potential mismatch between the initial focus and long-term ambitions."
#     ],
#     "green_flags": [
#       "Flag 1: The startup's beachhead is credible, with a validated market size in the MENA region.",
#       "Flag 2: The market is growing at a moderate rate, with a potential for expansion."
#     ],
#     "score_numeric": 40,
#     "rubric_rating": "Medium"
#   },
#   "traction_report": {
#     "score": "2/5",
#     "explanation": "The startup has shown early interest with a waitlist status of 'None' and an execution velocity of shipping an MVP in 7 months, indicating a moderate pace. However, the lack of users and revenue limits the score to 2.",
#     "confidence_level": "Medium",
#     "velocity_analysis": "Slow - The startup has made progress, but it has taken 7 months to reach MVP development, which is slower than expected for a pre-seed stage.",
#     "red_flags": [
#       "Flag 1: 'No clear feedback loops. Stagnant velocity.'"
#     ],
#     "green_flags": [
#       "Flag 1: 'Rapid shipping velocity'"
#     ],
#     "score_numeric": 40
#   },
#   "gtm_report": {
#     "score": "1/5",
#     "explanation": "The startup relies on 'Word of mouth / Community Direct Sales' with 0 users, indicating a lack of clear GTM thinking. The calculator flagged 'Insolvent Model' due to the price point of $0, and 'Ghost Ship' due to the absence of any activity. Additionally, the ICP is not defined, and the founders have no process for sales.",
#     "confidence_level": "High",
#     "key_strengths": [
#       "None"
#     ],
#     "key_weaknesses": [
#       "Reliance on passive Word of mouth with 0 users",
#       "No clear ICP defined",
#       "Calculator flagged 'Insolvent Model' and 'Ghost Ship'",
#       "Founders have no process for sales"
#     ],
#     "score_numeric": 20
#   },
#   "business_report": {
#     "score": "1/5",
#     "explanation": "The startup's Freemium pricing model with a 0% gross margin and a rapidly depleting burn rate suggests a significant risk of financial distress. The logic of the model is flawed due to the inability to cover the cost of serving and acquiring users.",
#     "confidence_level": "High",
#     "profitability_verdict": "Flawed Logic",
#     "red_flags": [
#       "Flag 1: Gross Margin: 0% - Significantly below the industry average of >70% for SaaS/AI startups, indicating a major operational challenge.",
#       "Flag 2: Unit Economics: Price ($0.0) is insufficient to cover the cost of serving and acquiring users, creating a precarious balance.",
#       "Flag 3: Runway: 0.0 months - A critical risk, highlighting a lack of financial stability and potential for immediate collapse."
#     ],
#     "green_flags": [],
#     "score_numeric": 20
#   },
#   "vision_report": {
#     "score": "2/5",
#     "explanation": "The founder's vision is ambitious, but the market analysis reveals significant contradictions and risks. The category play emphasizes validation, but the customer obsession focuses on speed. The differentiation relies on 'Deep Tech,' while the moat is 'First Mover Advantage.' The risk report shows no critical vision risks, but the contradiction report highlights several logic gaps. The market analysis confirms a 'Disruptor' category verdict with a 'High' scalability outlook, but the founder's vision is not fully aligned with the market reality.",
#     "confidence_level": "Medium",
#     "narrative_check": "Contradictory - The founder's vision and market analysis do not fully align.",
#     "red_flags": [
#       "Flag 1: 'Ambition Mismatch' - The founder claims to be the 'Global OS for Logistics,' but the Category Definition is 'A Whatsapp Chatbot.'",
#       "Flag 2: 'Wrong Medicine' - The customer obsession focuses on speed, while the category play emphasizes validation.",
#       "Flag 3: 'Tech-Brand Disconnect' - Differentiation relies on 'Deep Tech' while Moat is 'First Mover Advantage.'",
#       "Flag 4: 'Ostrich' - Risk blindness - the founder is ignoring potential regulatory and technical hurdles."
#     ],
#     "green_flags": [
#       "Flag 1: 'High Future Necessity Score' - The market analysis confirms a 'High' future necessity score.",
#       "Flag 2: 'Clear Data Moat' - The market analysis confirms a 'Clear Data Moat' with a 'Disruptor' category verdict."
#     ],
#     "score_numeric": 40
#   },
#   "operations_report": {
#     "score": "1/5",
#     "explanation": "The startup's plan is marred by several red flags, including a 'Dead Equity' cap table, a 'Desperation Raise' with a runway of less than 6 months, and a 'Financial Irresponsibility' burn rate of over $50k with $0 revenue. The 'Cart Before the Horse' contradiction, where funds are being spent on a sales team before the product exists, further raises concerns about the startup's operational readiness and fundability.",
#     "confidence_level": "High",
#     "deal_killer_check": "Broken - Dead Equity, Desperation Raise, and Financial Irresponsibility",
#     "red_flags": [
#       "Flag 1: Dead Equity - Founders own less than 60% of the company",
#       "Flag 2: Desperation Raise - Runway of less than 6 months",
#       "Flag 3: Financial Irresponsibility - Burn rate of over $50k with $0 revenue",
#       "Flag 4: Cart Before the Horse - Spending on sales team before product exists"
#     ],
#     "green_flags": [],
#     "score_numeric": 20
#   },
#   "final_report": {
#     "investor_output": {
#       "executive_summary": "This Pre-Seed opportunity presents a 'Hook' of a clear problem statement with high frequency among early-stage founders. However, this is critically anchored by a complete lack of a defined product or solution, making the venture uninvestable in its current state. With a weighted score of 17.3/45, the verdict is Pass (Not Ready), primarily due to the absence of a product and severe business model and operational deficiencies.",
#       "weighted_score": 17.3,
#       "verdict": "Pass (Not Ready)",
#       "deal_breakers": [
#         "No clear solution or product provided.",
#         "Freemium pricing model with a 0% gross margin and a rapidly depleting burn rate.",
#         "Dead Equity cap table, Desperation Raise with runway < 6 months, and Financial Irresponsibility burn rate > $50k with $0 revenue."
#       ],
#       "diligence_questions": [
#         "Given the complete absence of a product, what is the immediate plan to develop a functional MVP, and what specific technical milestones will be achieved in the next 90 days?",
#         "How do you intend to pivot from a $0 pricing model with 0% gross margin to a sustainable business that can cover operational costs and achieve profitability?",
#         "With founders owning less than 60% and a runway of less than 6 months, what is the strategy to secure further funding and align the cap table for future investment rounds?"
#       ],
#       "scorecard_grid": {
#         "team": 2.5,
#         "problem": 3.5,
#         "product": 0.0,
#         "market": 2.0,
#         "traction": 2.0,
#         "gtm": 1.0,
#         "business": 1.0,
#         "vision": 2.0,
#         "operations": 1.0
#       },
#       "dimension_rationales": [
#         {
#           "dimension": "Team",
#           "rationale": "The team possesses strong AI engineering skills but lacks crucial domain expertise and demonstrable execution capability in startup evaluation."
#         },
#         {
#           "dimension": "Problem",
#           "rationale": "The problem is well-defined and frequent, but founder alignment and scope mismatches between customer and market raise concerns."
#         },
#         {
#           "dimension": "Product",
#           "rationale": "There is a complete absence of a defined solution or product, rendering the venture unassessable."
#         },
#         {
#           "dimension": "Market",
#           "rationale": "The beachhead market is credible, but significant risks exist due to established competitors and unclear expansion strategies."
#         },
#         {
#           "dimension": "Traction",
#           "rationale": "Early interest exists, but the lack of users and revenue significantly limits the traction score."
#         },
#         {
#           "dimension": "GTM",
#           "rationale": "The Go-to-Market strategy is undefined, relying on word-of-mouth with zero users and no clear sales process."
#         },
#         {
#           "dimension": "Business",
#           "rationale": "The business model is fundamentally flawed with a 0% gross margin, $0 price point, and an unsustainable burn rate."
#         },
#         {
#           "dimension": "Vision",
#           "rationale": "The founder's vision is ambitious but misaligned with the market reality and lacks clear strategic coherence."
#         },
#         {
#           "dimension": "Operations",
#           "rationale": "Operational readiness is critically low, marked by a 'Dead Equity' cap table, 'Desperation Raise', and 'Cart Before the Horse' spending."
#         }
#       ]
#     },
#     "founder_output": {
#       "executive_summary": "Your application highlights a clear understanding of a significant problem faced by early-stage founders. However, the current execution falls far short of your ambitious vision, particularly concerning the absence of a defined product and a viable business model.",
#       "scorecard_grid": {
#         "team": 2.5,
#         "problem": 3.5,
#         "product": 0.0,
#         "market": 2.0,
#         "traction": 2.0,
#         "gtm": 1.0,
#         "business": 1.0,
#         "vision": 2.0,
#         "operations": 1.0
#       },
#       "dimension_analysis": [
#         {
#           "dimension": "Team",
#           "score": 2.5,
#           "confidence_level": "Medium",
#           "description": "You have a strong technical foundation in AI engineering, which is a significant asset. However, there are notable gaps in domain expertise relevant to startup validation and a lack of demonstrated execution capability in this specific area. Your alignment with the problem statement needs to be more clearly articulated through your background and experience.",
#           "justification": "Evidence points to AI engineering experience at Tabaani and Praxilab, and a clear understanding of the problem statement. However, prior experience gaps in startup evaluation and a lack of demonstrable alignment with the problem statement and solution are noted.",
#           "red_flags": [
#             "Management & Execution Risk - Prior experience gaps in the specific domain of startup evaluation pose a risk to the team\u2019s ability to effectively validate ideas and execute the business plan.",
#             "Founder-Market Fit Alignment Risk - The founder\u2019s background, while technically strong, doesn\u2019t demonstrably align with the problem statement and solution, suggesting a lack of genuine understanding of the target market.",
#             "Velocity Risk - The execution history shows a significant delay between initial concept and MVP development, indicating a potential risk of delayed market entry and missed opportunities."
#           ],
#           "improvements": [
#             "Seek advisors with deep experience in startup validation and early-stage market research.",
#             "Clearly articulate how your AI engineering skills directly translate to solving the specific market research challenges for early-stage founders."
#           ]
#         },
#         {
#           "dimension": "Problem",
#           "score": 3.5,
#           "confidence_level": "Medium",
#           "description": "The problem you've identified regarding early-stage founder validation is highly relevant and frequently encountered. While the pain points are confirmed, there are inconsistencies in founder alignment and a mismatch between your defined customer profile and your intended beachhead market. Furthermore, the current proposed solution of generic LLMs doesn't directly address the core need for specialized market research tools.",
#           "justification": "High frequency of the problem (56% of startups failing due to lack of validation) and confirmed pain points through search evidence are strengths. However, founder alignment mismatch and scope mismatch between customer profile and beachhead market are significant concerns.",
#           "red_flags": [
#             "Founder Alignment Mismatch - Founder's background in accounting is different from the customer profile.",
#             "Scope Mismatch - Customer Profile ('Microbus Drivers') is specific, while Beachhead Market ('All Transport in Africa') is broader.",
#             "Evidence Contradiction - Current solution (generic LLMs) does not directly address the need for better market research tools."
#           ],
#           "improvements": [
#             "Refine your customer profile to be more specific and align it with your beachhead market, or vice-versa.",
#             "Clearly define how your solution will leverage LLMs to provide specialized market research insights, not just generic text generation."
#           ]
#         },
#         {
#           "dimension": "Product",
#           "score": 0.0,
#           "confidence_level": "Low",
#           "description": "Currently, there is no discernible product or solution presented. This is the most critical area requiring immediate attention. Without a defined product, it's impossible to assess its viability, technical feasibility, or market fit.",
#           "justification": "No clear solution or product provided. Incomplete forensic tool reports and lack of essential product details.",
#           "red_flags": [
#             "No clear solution or product provided.",
#             "Incomplete forensic tool reports."
#           ],
#           "improvements": [
#             "Develop a detailed product roadmap outlining features, functionality, and a clear MVP definition.",
#             "Build a functional MVP that directly addresses the identified problem statement."
#           ]
#         },
#         {
#           "dimension": "Market",
#           "score": 2.0,
#           "confidence_level": "Medium",
#           "description": "Your chosen beachhead market is credible, and the market is experiencing moderate growth. However, the competitive landscape presents a significant 'David vs. Goliath' challenge with established tech giants. Your expansion plan lacks clarity, and there are logical contradictions that suggest potential strategic vulnerabilities in your market approach.",
#           "justification": "Credible beachhead market and moderate market growth are strengths. However, the 'David vs. Goliath' aspect, 'Teleportation' contradiction, and 'Non-Sequitur' contradiction pose significant risks.",
#           "red_flags": [
#             "'David vs. Goliath' aspect is a significant risk due to the presence of established tech giants like Google, Microsoft, and Amazon.",
#             "'Teleportation' contradiction highlights a potential issue with the startup's location and beachhead market.",
#             "'Non-Sequitur' contradiction indicates a lack of clear expansion dynamics and a potential mismatch between the initial focus and long-term ambitions."
#           ],
#           "improvements": [
#             "Clearly articulate your unique value proposition and defensible moat against larger competitors.",
#             "Develop a concrete and logical expansion strategy beyond the initial beachhead."
#           ]
#         },
#         {
#           "dimension": "Traction",
#           "score": 2.0,
#           "confidence_level": "Medium",
#           "description": "You've demonstrated a moderate pace in shipping an MVP, which is a positive sign. However, the current traction is severely limited by the absence of users and revenue. This indicates a need to move beyond development and focus on market validation and customer acquisition.",
#           "justification": "'Rapid shipping velocity' is a strength. However, 'No clear feedback loops. Stagnant velocity.' and lack of users/revenue are critical weaknesses.",
#           "red_flags": [
#             "'No clear feedback loops. Stagnant velocity.'",
#             "Lack of users and revenue."
#           ],
#           "improvements": [
#             "Implement robust user feedback mechanisms to iterate on your product.",
#             "Focus on acquiring your first paying customers and generating revenue."
#           ]
#         },
#         {
#           "dimension": "GTM",
#           "score": 1.0,
#           "confidence_level": "High",
#           "description": "Your current Go-to-Market strategy is underdeveloped, relying solely on 'Word of mouth / Community Direct Sales' with no existing users. This approach is not viable without a defined Ideal Customer Profile (ICP) or a structured sales process. The pricing model of $0 also indicates a lack of commercial strategy.",
#           "justification": "Reliance on 'Word of mouth / Community Direct Sales' with 0 users, undefined ICP, and no founder sales process are critical weaknesses.",
#           "red_flags": [
#             "Undefined ICP.",
#             "No founder process for sales.",
#             "Reliance on 'Word of mouth / Community Direct Sales' with 0 users."
#           ],
#           "improvements": [
#             "Define your Ideal Customer Profile (ICP) and develop targeted outreach strategies.",
#             "Establish a clear and repeatable sales process, even if it's initially manual."
#           ]
#         },
#         {
#           "dimension": "Business",
#           "score": 1.0,
#           "confidence_level": "High",
#           "description": "The current business model is unsustainable. A Freemium model with a 0% gross margin and a $0 price point means you cannot cover the costs of serving or acquiring users. This, combined with a rapidly depleting burn rate, presents an immediate financial risk.",
#           "justification": "Gross Margin: 0%, Unit Economics: Price ($0.0) insufficient to cover costs, and Runway: 0.0 months are critical financial red flags.",
#           "red_flags": [
#             "Gross Margin: 0% - Significantly below the industry average of >70% for SaaS/AI startups, indicating a major operational challenge.",
#             "Unit Economics: Price ($0.0) is insufficient to cover the cost of serving and acquiring users, creating a precarious balance.",
#             "Runway: 0.0 months - A critical risk, highlighting a lack of financial stability and potential for immediate collapse."
#           ],
#           "improvements": [
#             "Develop a pricing strategy that ensures a positive gross margin and covers unit economics.",
#             "Create a realistic financial model with a clear path to profitability."
#           ]
#         },
#         {
#           "dimension": "Vision",
#           "score": 2.0,
#           "confidence_level": "Medium",
#           "description": "Your vision is ambitious, aiming to be the 'Global OS for Logistics,' but it's currently misaligned with your defined category as a 'Whatsapp Chatbot.' There are contradictions in your customer obsession (speed vs. validation) and your differentiation strategy (Deep Tech vs. First Mover Advantage). You need to ensure your vision is grounded in market reality and strategic coherence.",
#           "justification": "Ambition Mismatch ('Global OS for Logistics' vs. 'Whatsapp Chatbot'), Wrong Medicine (speed vs. validation), and Tech-Brand Disconnect (Deep Tech vs. First Mover Advantage) are key vision risks.",
#           "red_flags": [
#             "'Ambition Mismatch' - The founder claims to be the 'Global OS for Logistics,' but the Category Definition is 'A Whatsapp Chatbot.'",
#             "'Wrong Medicine' - The customer obsession focuses on speed, while the category play emphasizes validation.",
#             "'Tech-Brand Disconnect' - Differentiation relies on 'Deep Tech' while Moat is 'First Mover Advantage.'",
#             "'Ostrich' - Risk blindness - the founder is ignoring potential regulatory and technical hurdles."
#           ],
#           "improvements": [
#             "Clearly define your category and ensure your vision aligns with it.",
#             "Reconcile the contradictions in your differentiation and customer focus strategies."
#           ]
#         },
#         {
#           "dimension": "Operations",
#           "score": 1.0,
#           "confidence_level": "High",
#           "description": "Your operational plan is severely flawed. The 'Dead Equity' cap table, a 'Desperation Raise' with a runway of less than 6 months, and 'Financial Irresponsibility' with a high burn rate and no revenue are critical issues. Furthermore, spending on a sales team before having a product is a 'Cart Before the Horse' scenario that indicates a lack of operational readiness.",
#           "justification": "Dead Equity, Desperation Raise, Financial Irresponsibility, and Cart Before the Horse are critical operational red flags.",
#           "red_flags": [
#             "Dead Equity - Founders own less than 60% of the company",
#             "Desperation Raise - Runway of less than 6 months",
#             "Financial Irresponsibility - Burn rate of over $50k with $0 revenue",
#             "Cart Before the Horse - Spending on sales team before product exists"
#           ],
#           "improvements": [
#             "Restructure the cap table to ensure founder control and alignment.",
#             "Prioritize product development over premature sales team expansion."
#           ]
#         }
#       ],
#       "top_3_priorities": [
#         "1. Develop and launch a functional MVP that directly addresses the core problem.",
#         "2. Define and validate a sustainable business model with a clear pricing strategy and positive unit economics.",
#         "3. Establish a clear Go-to-Market strategy with a defined ICP and a plan for customer acquisition."
#       ],
#       "weighted_score": 17.3,
#       "verdict": "Pass (Not Ready)"
#     }
#   }
# }

# def format_evaluation(source_data):
#     # Locate the list of dimension analysis
#     dimensions = source_data["final_report"]["founder_output"]["dimension_analysis"]
    
#     # Mapping source names to your desired keys
#     key_mapping = {
#         "Team": "team",
#         "Problem": "problem",
#         "Product": "product",
#         "Market": "market",
#         "Traction": "traction",
#         "GTM": "gtm",
#         "Business": "economics",
#         "Vision": "vision",
#         "Operations": "ops"
#     }
    
#     scores_dict = {}
    
#     for item in dimensions:
#         dim_name = item["dimension"]
#         if dim_name in key_mapping:
#             target_key = key_mapping[dim_name]
#             scores_dict[target_key] = {
#                 "score": item["score"],
#                 "description": item["description"]
#             }
            
#     # Constructing the final object
#     evaluation_output = {
#         "stage": "Pre-Seed", # Can be hardcoded or extracted if present in other fields
#         "scores": scores_dict,
#         "company_context": source_data["final_report"]["founder_output"]["executive_summary"]
#     }
    
#     return evaluation_output

# # Usage
# EVAL_OUTPUT = format_evaluation(data)
# # print(json.dumps(evaluation_output, indent=4))
# # EVAL_OUTPUT = {
# #     "stage": "Pre-Seed",
# #     "scores": {
# #         "team": {"score": 3, "description": "Solo founder with strong technical background but no sales experience"},
# #         "problem": {"score": 2, "description": "Vague customer language and conceptual problem framing"},
# #         "product": {"score": 2, "description": "Prototype built but many features unused, unknown user behavior"},
# #         "market": {"score": 2, "description": "Unclear ICP definition, overstated TAM"},
# #         "traction": {"score": 1, "description": "100 signups but only 5 active weekly users, low retention"},
# #         "gtm": {"score": 1, "description": "Not selling, trying multiple channels with no clear winner"},
# #         "economics": {"score": 2, "description": "6 months runway, pricing not tested, low ARPU"},
# #         "vision": {"score": 5, "description": "Compelling long-term vision, strong narrative"},
# #         "ops": {"score": 3, "description": "No weekly planning, reactive execution"}
# #     },
# #     "company_context": "Neuro-productivity hardware helping knowledge workers optimize focus through EEG tracking."
# # }

# if __name__ == "__main__":
#     if not MY_API_KEY:
#         print("[ERROR] GEMINI_API_KEY not found. Please check your .env file.")
#         print("\nTo fix this:")
#         print("1. Create a .env file in the project root if it doesn't exist")
#         print("2. Add: GEMINI_API_KEY=your_api_key_here")
#         print("3. Get your API key from: https://aistudio.google.com/apikey")
#     else:
#         print("--- STARTING RECOMMENDATION AGENT ---")
#         print(f"Using API Key: {MY_API_KEY[:10]}...{MY_API_KEY[-4:] if len(MY_API_KEY) > 14 else '***'}")
        
#         try:
#             # Execute the workflow
#             result = run_recommendation_agent(RAW_INPUT, EVAL_OUTPUT, MY_API_KEY, save_output=True)
            
#             # Handle tuple return (report, output_paths)
#             if isinstance(result, tuple):
#                 report, output_paths = result
#                 print("\n--- FINAL REPORT ---\n")
#                 print(report)
#                 print("\n" + "=" * 80)
#                 print("OUTPUT FILES SAVED:")
#                 print("=" * 80)
#                 print(f"Request ID: {output_paths['request_id']}")
#                 print(f"Folder: {output_paths['folder']}")
#                 print(f"\nFiles created:")
#                 for file_type, file_path in output_paths['files'].items():
#                     print(f"  - {file_type.upper()}: {file_path}")
#             else:
#                 # Backward compatibility
#                 print("\n--- FINAL REPORT ---\n")
#                 print(result)
                
#         except ValueError as e:
#             print(f"\n{e}")
#             print("\nFor more help, see: RUN_INSTRUCTIONS.md")
#         except Exception as e:
#             print(f"\n[ERROR] Unexpected error: {e}")
#             print("\nPlease check:")
#             print("1. Your API key is valid and active")
#             print("2. You have internet connection")
#             print("3. The Gemini API is accessible")

