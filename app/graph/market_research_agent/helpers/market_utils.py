import json
import http.client
import os
import requests
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import yfinance as yf
import datetime
from pytrends.request import TrendReq
from app.core.config import Config, gemini_client
from app.core.rate_limiter import call_gemini
from app.graph.market_research_agent import prompts
from app.core.logger import get_logger

logger = get_logger("MarketUtils")

SERPER_API_KEY = Config.SERPER_API_KEY

def fetch_stock_data(ticker_symbol: str, period: str = "2y"):
    """
    Fetches historical stock data for a given ticker.
    """
    logger.info(f"\n[DOWNLOAD] [Tool 1] Fetching data for: {ticker_symbol}...")
    try:
        # Initialize Ticker
        stock = yf.Ticker(ticker_symbol)
        df = stock.history(period=period, auto_adjust=True)
        
        if df.empty:
            logger.error(f"[ERROR] Error: No data found for symbol '{ticker_symbol}'.")
            return None
        
        # Clean Data
        df.reset_index(inplace=True)
        df.columns = [c.lower() for c in df.columns]
        df['date'] = pd.to_datetime(df['date']).dt.date
        
        # Save to CSV
        os.makedirs("data_output", exist_ok=True)
        filename = f"data_output/{ticker_symbol}_market_data.csv"
        df.to_csv(filename, index=False)
        
        logger.info(f"[SUCCESS] Success: Fetched {len(df)} rows.")
        return filename

    except Exception as e:
        logger.warning(f"[WARNING] Fetch Error: {e}")
        return None

def calculate_technical_indicators(input_file: str):
    """
    Calculates SMA (Trend) and RSI (Momentum) indicators.
    """
    logger.info(f"\n[TREND UP] [Tool 2] Calculating indicators...")
    try:
        if not os.path.exists(input_file):
            logger.error("[ERROR] Error: Input file not found.")
            return None
            
        df = pd.read_csv(input_file)
        
        # Calculate Simple Moving Average (20-day trend)
        df['SMA_20'] = df['close'].rolling(window=20).mean()
        
        # Calculate RSI (14-day momentum)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI_14'] = 100 - (100 / (1 + rs))
        
        # Drop rows with NaN (created by calculation lag)
        df.dropna(inplace=True)
        
        # Save Output
        output_file = input_file.replace(".csv", "_analyzed.csv")
        df.to_csv(output_file, index=False)
        
        logger.info(f"[SUCCESS] Success: Added SMA and RSI columns.")
        return output_file

    except Exception as e:
        logger.warning(f"[WARNING] Math Error: {e}")
        return None

def get_trending_data(keywords, geo_code='EG'):
    logger.info(f"   [DATA] Querying Google Trends for: {keywords}...")
    try:
        pytrends = TrendReq(hl='en-US', tz=360)
        pytrends.build_payload(keywords, cat=0, timeframe='today 12-m', geo=geo_code)
        data = pytrends.interest_over_time()
        if data.empty: raise Exception("Empty")
        if 'isPartial' in data.columns: del data['isPartial']
        return data, "Google Trends"
    except Exception as e:
        logger.warning(f"   [WARNING] Trends Error: {e}")
        return None, None

def plot_trends(data, source_name, col):
    start_avg = data[col].head(30).mean()
    end_avg = data[col].tail(30).mean()
    
    if start_avg == 0: start_avg = 1 
    growth_pct = ((end_avg - start_avg) / start_avg) * 100
    
    stats = pd.DataFrame({
        'metric': ['growth_pct', 'start_avg', 'end_avg', 'source'],
        'value': [growth_pct, start_avg, end_avg, source_name]
    })
    os.makedirs("data_output", exist_ok=True)
    stats.to_csv("data_output/market_stats.csv", index=False)

    plt.figure(figsize=(10, 6), facecolor='#F0EADC')
    ax = plt.gca()
    ax.set_facecolor('#F0EADC')
    plt.plot(data.index, data[col], label=f"{source_name} (Growth: {growth_pct:.1f}%)", color='#2ca02c') 
    
    z =  pd.Series(range(len(data)))
    p =  pd.Series(data[col].values)
    m, b =  (p.cov(z) / z.var()), p.mean() - (p.cov(z) / z.var()) * z.mean() # Simple Linear Regression
    plt.plot(data.index, m*z + b, color='red', linestyle='--', alpha=0.5, label="Trendline")

    plt.title(f"Market Demand: 12-Month Trend ({source_name})")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.savefig(f"data_output/market_demand_chart.png")
    data.to_csv(f"data_output/market_trends.csv")
    plt.close()
    
    # --- DYNAMIC ANALYSIS ---
    try:
        recent_data = str(data[col].tail(10).values.tolist())
        prompt = prompts.trend_analysis_prompt(growth_pct, source_name, recent_data)
        res = call_gemini(prompt)
        analysis_text = res.text.strip().replace('"', '')
        with open("data_output/trend_analysis.txt", "w") as f:
            f.write(analysis_text)
    except Exception as e:
        logger.warning(f"Trend Analysis Failed: {e}")
        # Fallback text
        with open("data_output/trend_analysis.txt", "w") as f:
            f.write(f"The market for {source_name} has shown a {growth_pct:.1f}% change over the last year. This trend indicates shifting consumer interest levels.")

    return growth_pct

def identify_industry(idea):
    try:
        prompt_ind = prompts.identify_industry_prompt(idea)
        res = call_gemini(prompt_ind)
        return res.text.strip().replace('"','')
    except Exception as e:
        logger.warning(f"   [WARNING] Industry ID Error: {e}")
        return idea


def search_market_reports(query):
    logger.info(f"   [SEARCH] Searching: '{query}'...")
    try:
        conn = http.client.HTTPSConnection("google.serper.dev")
        payload = json.dumps({ "q": query, "num": 5 })
        headers = {
            'X-API-KEY': SERPER_API_KEY,
            'Content-Type': 'application/json'
        }
        conn.request("POST", "/search", payload, headers)
        res = conn.getresponse()
        data = res.read()
        results = json.loads(data.decode("utf-8"))
        
        output = ""
        if "organic" in results:
            for item in results["organic"]:
                output += f"Title: {item.get('title')}\nSnippet: {item.get('snippet')}\n\n"
        return output
    except Exception as e:
        logger.warning(f"   [WARNING] Search Error: {e}")
        return ""

def fetch_industry_cagr(industry):
    logger.info(f"   [TREND UP] Fetching CAGR reports for '{industry}'...")
    query = f"{industry} market growth rate CAGR 2024"
    search_data = search_market_reports(query)
    
    if not search_data:
        return None
        
    try:
        prompt = prompts.extract_cagr_prompt(industry, search_data)
        res = call_gemini(prompt)
        # the prompt asks to return ONLY a float number
        import re
        matches = re.findall(r'-?[\d\.]+', res.text)
        if matches:
            return float(matches[0])
    except Exception as e:
        logger.warning(f"Error extracting CAGR: {e}")
        
    return None

import re

def extract_json_from_text(text):
    """
    Extracts the first valid JSON block from a string, handling markdown code blocks.
    """
    try:
        # 1. Try to find content within ```json ... ``` blocks
        match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        
        # 2. Try to find content within curly braces { ... }
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
            
        # 3. Fallback: try raw text if it looks like JSON
        return json.loads(text)
    except Exception as e:
        logger.warning(f"JSON Extraction Failed: {e}")
        return None

def analyze_market_size(idea, industry, location, market_data):
    logger.info("   [CALCULATE] triangulating market numbers...")
    analysis_prompt = prompts.analyze_market_size_prompt(idea, industry, location, market_data)
    
    try:
        res = call_gemini(analysis_prompt)
        # Use robust extractor
        data = extract_json_from_text(res.text)
        if data: return data
        
        # Fallback if extraction fails
        logger.warning("   [WARNING] JSON Extraction returned None. Using raw text fallback logic or error.")
        return None
    except Exception as e:
        logger.warning(f"   [WARNING] Sizing Analysis Error: {e}")
        return None

import re

def plot_market_funnel(result, industry):
    try:
        # FIXED: Helper to extract numbers AND handle units correctly
        def extract_scaled_num(text):
            if not text or str(text) == "Unknown" or str(text) == "Insufficient data": 
                return 0
            
            # Extract the raw digits
            matches = re.findall(r'[\d\.]+', str(text).replace(',', ''))
            if not matches: 
                return 0
                
            num = float(matches[0])
            text_lower = str(text).lower()
            
            # Scale the numbers so they are all relative to Millions
            if 'trillion' in text_lower:
                num *= 1_000_000
            elif 'billion' in text_lower:
                num *= 1_000
            elif 'thousand' in text_lower:
                num *= 0.001
                
            return num

        # Get the correctly scaled numbers
        tam_num = extract_scaled_num(result.get('tam_value'))
        sam_num = extract_scaled_num(result.get('sam_value'))
        som_num = extract_scaled_num(result.get('som_value'))
        
        # Fallback to visual defaults ONLY if data extraction completely fails
        if tam_num == 0 or sam_num == 0:
            sizes = [100, 20, 1]
        else:
            # Normalize sizes relative to TAM so the chart fits perfectly
            sizes = [
                100.0, 
                min((sam_num / tam_num) * 100, 100.0),  # Cap at 100% just in case
                min((som_num / tam_num) * 100, 100.0)
            ]
            # Ensure SOM is visible even if it's less than 1% of TAM
            sizes[2] = max(sizes[2], 1.0) 
            
        labels = [
            f"TAM\n{result.get('tam_value')}", 
            f"SAM\n{result.get('sam_value')}", 
            f"SOM\n{result.get('som_value')}" 
        ]
        
        colors = ['#ff9999', '#66b3ff', '#99ff99']
        
        plt.figure(figsize=(8, 6), facecolor='#F0EADC')
        ax = plt.gca()
        ax.set_facecolor('#F0EADC')
        
        plt.barh([3, 2, 1], sizes, color=colors, height=0.6)
        plt.yticks([3, 2, 1], ["TAM", "SAM", "SOM"])
        plt.xlabel("Market Potential (Relative to TAM)")
        plt.title(f"Market Sizing: {industry}")
        
        for i, v in enumerate(sizes):
            plt.text(v/2, 3-i, labels[i], ha='center', va='center', fontweight='bold', color='black')
            
        os.makedirs("data_output", exist_ok=True)
        plt.savefig("data_output/market_sizing_funnel.png")
        plt.close()
        return "data_output/market_sizing_funnel.png"
    except Exception as e:
        logger.warning(f"[WARNING] Sizing Visual Error: {e}")
        return None