import json
import aiohttp
import asyncio
import os
import http.client
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from app.core.config import Config, gemini_client
from app.core.rate_limiter import call_gemini
from app.graph.market_research_agent import prompts
from app.graph.market_research_agent.logger_config import get_logger

logger = get_logger("FinanceUtils")

SERPER_API_KEY = Config.SERPER_API_KEY

def detect_currency(idea):
    print(f"   🌍 Detecting location and currency for: '{idea}'...")
    try:
        prompt = prompts.detect_currency_prompt(idea)
        res = call_gemini(prompt)
        return json.loads(res.text.replace("```json","").replace("```","").strip())
    except:
        return {"country": "Global", "currency_code": "USD", "currency_symbol": "$"}

def search_cost_data(query):
    print(f"   🔎 Searching market for: '{query}'...")
    try:
        conn = http.client.HTTPSConnection("google.serper.dev")
        payload = json.dumps({ "q": query, "num": 5 })
        headers = { 'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json' }
        conn.request("POST", "/search", payload, headers)
        data = json.loads(conn.getresponse().read().decode("utf-8"))
        
        evidence = ""
        if "organic" in data:
            for item in data["organic"]:
                evidence += f"- {item.get('title')}: {item.get('snippet')} (Source: {item.get('link')})\n"
        return evidence
    except Exception as e:
        print(f"   ⚠️ Search failed: {e}")
        return ""

def get_real_world_estimates(idea, currency_context=None):
    if currency_context:
        loc_data = currency_context
        print(f"   🌍 Using existing location data: {loc_data.get('country')} ({loc_data.get('currency_code')})")
    else:
        loc_data = detect_currency(idea)
        
    curr_code = loc_data.get("currency_code", "USD")
    country = loc_data.get("country", "Global")
    
    print(f"   🤖 Identifying cost drivers in {country} ({curr_code})...")
    plan_prompt = prompts.financial_plan_prompt(idea, country, curr_code)
    try:
        res = call_gemini(plan_prompt)
        queries = json.loads(res.text.replace("```json","").replace("```","").strip())
    except:
        queries = [f"commercial rent prices {country}", f"average salary {country}", f"coffee bean price {country}"]

    market_data = ""
    # LIMIT TO 2 QUERIES TO SAVE QUOTA
    for q in queries[:2]:
        market_data += search_cost_data(q) + "\n"
        
    print(f"   🧮 Extracting {curr_code} financial model from search results...")
    return generate_financial_estimates(idea, market_data, curr_code)

def generate_financial_estimates(idea, market_data, currency_code):
    extract_prompt = prompts.financial_extraction_prompt(idea, market_data, currency_code)
    try:
        res = call_gemini(extract_prompt)
        return json.loads(res.text.replace("```json","").replace("```","").strip())
    except Exception as e:
        print(f"⚠️ Extraction Error: {e}")
        return None

def generate_financial_visuals(estimates):
    print("   📊 Generating Localized Financial Charts...")
    os.makedirs("data_output", exist_ok=True)
    
    curr = estimates.get("currency", "USD")
    startup = estimates["startup_costs"]
    monthly = estimates["monthly_fixed_costs"]
    rev = estimates["revenue_assumptions"]
    
    total_startup = sum(startup.values())
    total_monthly = sum(monthly.values())
    
    avg_ticket = rev.get("avg_ticket_price", 0)
    customers = rev.get("daily_customers", 0)
    monthly_rev = customers * avg_ticket * 30
    monthly_profit = monthly_rev - total_monthly
    
    try:
        plt.figure(figsize=(8, 8), facecolor='#F0EADC')
        plt.pie(startup.values(), labels=startup.keys(), autopct='%1.1f%%', colors=plt.cm.Pastel1.colors)
        plt.title(f"Startup Costs in {curr}\nTotal: {total_startup:,.0f} {curr}")
        plt.savefig("data_output/finance_startup_pie.png")
        plt.close()
        
        months = np.arange(0, 25)
        
        # Realistic Growth Curve (Sigmoid-like ramp up over 12 months)
        # Revenue starts at 10% and grows to 100% by month 12
        growth_factor = 1 / (1 + np.exp(-0.5 * (months - 6))) 
        # Normalize to 0.1 - 1.0 range approx
        growth_factor = (growth_factor - growth_factor.min()) / (growth_factor.max() - growth_factor.min()) * 0.9 + 0.1
        
        # Monthly Profit = (Max Revenue * Growth Factor) - Fixed Costs
        # Note: Valid only for months > 0. Month 0 is just startup cost.
        monthly_profits = (monthly_rev * growth_factor) - total_monthly
        monthly_profits[0] = -total_monthly # Month 0 is pure loss/setup
        
        # Cumulative Cash Flow
        cash_flow = -total_startup + np.cumsum(monthly_profits)
        
        # Find break-even month (first month where cash_flow > 0)
        break_even_indices = np.where(cash_flow > 0)[0]
        break_even_month = break_even_indices[0] if len(break_even_indices) > 0 else 99
        
        plt.figure(figsize=(10, 6), facecolor='#F0EADC')
        ax = plt.gca()
        ax.set_facecolor('#F0EADC')
        plt.plot(months, cash_flow, label=f'Net Cash ({curr})', color='green', linewidth=2)
        plt.axhline(0, color='black', linestyle='--')
        plt.title(f"Break-Even Analysis (Profit: {monthly_profit:,.0f} {curr}/mo)")
        plt.xlabel("Months")
        plt.ylabel(f"Cash Position ({curr})")
        plt.grid(True, alpha=0.3)
        plt.legend()
        plt.savefig("data_output/finance_breakeven_line.png")
        plt.close()
    except Exception as e:
        print(f"❌ Chart Generation Failed: {e}")
        # Ensure plot is closed even if error occurs
        plt.close()
    
    summary = {
        "Metric": ["Currency", "Total Startup", "Monthly Expenses", "Monthly Revenue", "Net Profit", "Break-Even Month"],
        "Value": [curr, total_startup, total_monthly, monthly_rev, monthly_profit, break_even_month]
    }
    pd.DataFrame(summary).to_csv("data_output/finance_summary.csv", index=False)
    
    # --- DYNAMIC ANALYSIS ---
    try:
        prompt = prompts.financial_analysis_prompt(total_startup, curr, break_even_month, monthly_profit)
        res = call_gemini(prompt)
        analysis_text = res.text.strip().replace('"', '')
        with open("data_output/financial_analysis.txt", "w") as f:
            f.write(analysis_text)
    except Exception as e:
        logger.warning(f"Financial Analysis Failed: {e}")
        with open("data_output/financial_analysis.txt", "w") as f:
            f.write(f"Estimated startup costs are {total_startup:,.0f} {curr} with a projected break-even at month {break_even_month}. Careful cash flow management is recommended.")
    
    # Save raw estimates to JSON for final report compilation
    with open("data_output/finance_estimates.json", "w") as f:
        json.dump(estimates, f, indent=4)
    
    with open("data_output/finance_sources.txt", "w") as f:
        f.write("SOURCES USED:\n")
        for s in estimates.get("sources_used", []): f.write(f"- {s}\n")
            
    print(f"✅ Success: Financials built in {curr}.")
    return "data_output/finance_summary.csv"

def run_finance_model(idea):
    print(f"\n💰 [Tool 8] Starting Localized Financial Model...")
    estimates = get_real_world_estimates(idea)
    return generate_financial_visuals(estimates)
