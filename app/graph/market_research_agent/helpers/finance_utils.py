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
from app.core.logger import get_logger

logger = get_logger("FinanceUtils")

SERPER_API_KEY = Config.SERPER_API_KEY

def detect_currency(idea):
    print(f"   [GLOBAL] Detecting location and currency for: '{idea}'...")
    try:
        prompt = prompts.detect_currency_prompt(idea)
        res = call_gemini(prompt)
        return json.loads(res.text.replace("```json","").replace("```","").strip())
    except:
        return {"country": "Global", "currency_code": "USD", "currency_symbol": "$"}

def search_cost_data(query):
    print(f"   [SEARCH] Searching market for: '{query}'...")
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
        print(f"   [WARNING] Search failed: {e}")
        return ""

def get_real_world_estimates(idea, currency_context=None):
    if currency_context:
        loc_data = currency_context
        print(f"   [GLOBAL] Using existing location data: {loc_data.get('country')} ({loc_data.get('currency_code')})")
    else:
        loc_data = detect_currency(idea)
        
    curr_code = loc_data.get("currency_code", "USD")
    country = loc_data.get("country", "Global")
    
    print(f"   [AI] Identifying cost drivers in {country} ({curr_code})...")
    plan_prompt = prompts.financial_plan_prompt(idea, country, curr_code)
    try:
        res = call_gemini(plan_prompt)
        queries = json.loads(res.text.replace("```json","").replace("```","").strip())
    except:
        queries = [f"commercial rent prices {country}", f"average salary {country}", f"coffee bean price {country}"]

    market_data = ""
    for q in queries[:5]:
        market_data += search_cost_data(q) + "\n"
        
    print(f"   [CALCULATE] Extracting {curr_code} financial model from search results...")
    return generate_financial_estimates(idea, market_data, curr_code)

def generate_financial_estimates(idea, market_data, currency_code):
    extract_prompt = prompts.financial_extraction_prompt(idea, market_data, currency_code)
    try:
        res = call_gemini(extract_prompt)
        return json.loads(res.text.replace("```json","").replace("```","").strip())
    except Exception as e:
        print(f"[WARNING] Extraction Error: {e}")
        return None

def generate_financial_visuals(estimates):
    print("   [DATA] Generating Localized Financial Charts...")
    os.makedirs("data_output", exist_ok=True)
    
    curr = estimates.get("currency", "USD")
    startup = estimates["startup_costs"]
    monthly = estimates["monthly_fixed_costs"]
    rev = estimates["revenue_assumptions"]
    
    # Sanitize and prepare startup values
    clean_startup = {}
    for k, v in startup.items():
        try:
            val = float(v)
            if not np.isnan(val) and val > 0:
                clean_startup[k] = val
        except:
            pass
            
    total_startup = sum(clean_startup.values())
    total_monthly = sum(monthly.values())
    
    avg_ticket = rev.get("avg_ticket_price", 0)
    customers = rev.get("daily_customers", 0)
    monthly_rev = customers * avg_ticket * 30
    monthly_profit = monthly_rev - total_monthly
    
    # Initialize variables to prevent UnboundLocalError
    break_even_month = 99
    runway_months = 24
    
    try:
        plt.figure(figsize=(8, 8), facecolor='#F0EADC')
        if total_startup > 0:
            plt.pie(clean_startup.values(), labels=clean_startup.keys(), autopct='%1.1f%%', colors=plt.cm.Pastel1.colors)
        else:
            plt.pie([1], labels=["No Data"], colors=['#cccccc'])
        plt.title(f"Startup Costs in {curr}\nTotal: {total_startup:,.0f} {curr}")
        plt.savefig("data_output/finance_startup_pie.png")
        plt.close()
        
        months = np.arange(0, 25)
        
        # Realistic Growth Curve (Sigmoid-like ramp up over 12 months)
        # Revenue starts at 10% and grows to 100% by month 12
        growth_factor = 1 / (1 + np.exp(-0.5 * (months - 6))) 
        # Normalize to 0.1 - 1.0 range approx
        growth_factor = (growth_factor - growth_factor.min()) / (growth_factor.max() - growth_factor.min()) * 0.9 + 0.1
        
        # Fix 1: Assume initial funding covers startup costs + 6 months of operating expenses 
        # (This is standard seed-stage logic)
        initial_capital = total_startup + (total_monthly * 6)
        
        # Monthly Profit calculation
        monthly_profits = (monthly_rev * growth_factor) - total_monthly
        monthly_profits[0] = -total_monthly # Month 0 is setup
        
        # Cumulative Cash Flow (Starting with the Capital in the bank minus setup costs)
        cash_flow = (initial_capital - total_startup) + np.cumsum(monthly_profits)
        
        # Find break-even month (first month where MONTHLY profit is > 0)
        break_even_indices = np.where(monthly_profits > 0)[0]
        
        # Check insolvency (When bank account hits 0)
        insolvent_indices = np.where(cash_flow < 0)[0]
        
        if len(insolvent_indices) > 0 and len(break_even_indices) == 0:
            # Runs out of cash, never breaks even
            break_even_month = 999 
            runway_months = insolvent_indices[0]
        elif len(insolvent_indices) > 0 and insolvent_indices[0] < break_even_indices[0]:
            # Runs out of cash BEFORE breaking even
            break_even_month = 999
            runway_months = insolvent_indices[0]
        elif len(break_even_indices) > 0:
            break_even_month = break_even_indices[0]
            # Runway is technically infinite if they break even before cash runs out
            runway_months = None 
        else:
            break_even_month = 99 
            runway_months = 24
        
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
        print(f"[ERROR] Chart Generation Failed: {e}")
        # Ensure plot is closed even if error occurs
        plt.close()
    
    summary = {
        "Metric": ["Currency", "Total Startup", "Monthly Expenses", "Monthly Revenue", "Net Profit", "Break-Even Month", "Runway Months"],
        "Value": [curr, total_startup, total_monthly, monthly_rev, monthly_profit, break_even_month, runway_months if runway_months else "N/A"]
    }
    pd.DataFrame(summary).to_csv("data_output/finance_summary.csv", index=False)
    
    # --- DYNAMIC ANALYSIS ---
    try:
        if break_even_month == 999:
           analysis_context = f"Total Startup: {total_startup}, Break-even: NEVER (Insolvent in {runway_months} months), Monthly Profit: {monthly_profit}"
        else:
           analysis_context = f"Total Startup: {total_startup}, Break-even: Month {break_even_month}, Monthly Profit: {monthly_profit}"

        prompt = prompts.financial_analysis_prompt(total_startup, curr, break_even_month if break_even_month not in [99, 999] else "NEVER", monthly_profit, runway_months)
        res = call_gemini(prompt)
        analysis_text = res.text.strip().replace('"', '')
        with open("data_output/financial_analysis.txt", "w") as f:
            f.write(analysis_text)
    except Exception as e:
        logger.warning(f"Financial Analysis Failed: {e}")
        with open("data_output/financial_analysis.txt", "w") as f:
            if break_even_month == 999:
                 f.write(f"Estimated startup costs are {total_startup:,.0f} {curr} but the business runs out of cash in {runway_months} months. Highly unsustainable.")
            elif break_even_month == 99:
                 f.write(f"Estimated startup costs are {total_startup:,.0f} {curr}. The business does not break even within 24 months, but survives with current capital.")
            else:
                 f.write(f"Estimated startup costs are {total_startup:,.0f} {curr} with a projected break-even at month {break_even_month}. Careful cash flow management is recommended.")
    
    # Save raw estimates to JSON for final report compilation
    with open("data_output/finance_estimates.json", "w") as f:
        json.dump(estimates, f, indent=4)
    
    with open("data_output/finance_sources.txt", "w") as f:
        f.write("SOURCES USED:\n")
        for s in estimates.get("sources_used", []): f.write(f"- {s}\n")
            
    print(f"[SUCCESS] Success: Financials built in {curr}.")
    return "data_output/finance_summary.csv"

def run_finance_model(idea):
    print(f"\n[FINANCE] [Tool 8] Starting Localized Financial Model...")
    estimates = get_real_world_estimates(idea)
    return generate_financial_visuals(estimates)
