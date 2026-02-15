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
    logger.info(f"\n📥 [Tool 1] Fetching data for: {ticker_symbol}...")
    try:
        # Initialize Ticker
        stock = yf.Ticker(ticker_symbol)
        df = stock.history(period=period, auto_adjust=True)
        
        if df.empty:
            logger.error(f"❌ Error: No data found for symbol '{ticker_symbol}'.")
            return None
        
        # Clean Data
        df.reset_index(inplace=True)
        df.columns = [c.lower() for c in df.columns]
        df['date'] = pd.to_datetime(df['date']).dt.date
        
        # Save to CSV
        os.makedirs("data_output", exist_ok=True)
        filename = f"data_output/{ticker_symbol}_market_data.csv"
        df.to_csv(filename, index=False)
        
        logger.info(f"✅ Success: Fetched {len(df)} rows.")
        return filename

    except Exception as e:
        logger.warning(f"⚠️ Fetch Error: {e}")
        return None

def calculate_technical_indicators(input_file: str):
    """
    Calculates SMA (Trend) and RSI (Momentum) indicators.
    """
    logger.info(f"\n📈 [Tool 2] Calculating indicators...")
    try:
        if not os.path.exists(input_file):
            logger.error("❌ Error: Input file not found.")
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
        
        logger.info(f"✅ Success: Added SMA and RSI columns.")
        return output_file

    except Exception as e:
        logger.warning(f"⚠️ Math Error: {e}")
        return None

def search_wikidata(query):
    """
    Searches Wikidata for the most likely entity and returns its English Wikipedia title.
    """
    logger.info(f"   🌐 Searching Wikidata for: '{query}'...")
    try:
        # 1. Search for the entity
        search_url = "https://www.wikidata.org/w/api.php"
        params = {
            "action": "wbsearchentities",
            "format": "json",
            "language": "en",
            "search": query
        }
        res = requests.get(search_url, params=params)
        data = res.json()
        
        if not data.get("search"):
            return "Business"
            
        # Get the first result's ID (e.g., Q12345)
        entity_id = data["search"][0]["id"]
        
        # 2. Get the Wikipedia Sitelink
        details_url = "https://www.wikidata.org/w/api.php"
        details_params = {
            "action": "wbgetentities",
            "ids": entity_id,
            "format": "json",
            "props": "sitelinks",
            "sitefilter": "enwiki"
        }
        res = requests.get(details_url, params=details_params)
        details = res.json()
        
        # Extract the title
        try:
            sitelinks = details["entities"][entity_id]["sitelinks"]
            if "enwiki" in sitelinks:
                title = sitelinks["enwiki"]["title"]
                # Convert spaces to underscores for the Pageviews API
                return title.replace(" ", "_")
        except: pass
        
        # Fallback main match label if no sitelink
        return data["search"][0]["label"].replace(" ", "_")
        
    except Exception as e:
        logger.warning(f"   ⚠️ Wikidata Error: {e}")
        
        try:
            logger.info("   🤖 Wikidata failed. Asking AI for the best Wikipedia topic...")
            fallback_prompt = prompts.wiki_fallback_prompt(query)
            res = call_gemini(fallback_prompt)
            return res.text.strip()
        except:
            return "Business"

def fetch_wikipedia_data(topic):
    logger.info(f"   📖 Switching to Wikipedia Data for: '{topic}'...")
    end = datetime.datetime.now()
    start = end - datetime.timedelta(days=365)
    url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents/{topic}/daily/{start.strftime('%Y%m%d')}/{end.strftime('%Y%m%d')}"
    headers = {'User-Agent': 'MarketResearchAgent/1.0'}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200: return None, None
        data = response.json()
        if 'items' not in data: return None, None
        
        dates = [datetime.datetime.strptime(item['timestamp'], "%Y%m%d00") for item in data['items']]
        views = [item['views'] for item in data['items']]
        return pd.DataFrame({'interest': views}, index=dates), f"Wikipedia Views: {topic}"
    except: return None, None

def get_trending_data(keywords, geo_code='EG'):
    logger.info(f"   📊 Querying Google Trends for: {keywords}...")
    try:
        pytrends = TrendReq(hl='en-US', tz=360)
        pytrends.build_payload(keywords, cat=0, timeframe='today 12-m', geo=geo_code)
        data = pytrends.interest_over_time()
        if data.empty: raise Exception("Empty")
        if 'isPartial' in data.columns: del data['isPartial']
        return data, "Google Trends"
    except Exception as e:
        logger.warning(f"   ⚠️ Trends Error: {e}")
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
        recent_data = str(data[col].tail(5).values.tolist())
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
        logger.warning(f"   ⚠️ Industry ID Error: {e}")
        return idea


def search_market_reports(query):
    logger.info(f"   🔎 Searching: '{query}'...")
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
        logger.warning(f"   ⚠️ Search Error: {e}")
        return ""

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
    logger.info("   🧮 triangulating market numbers...")
    analysis_prompt = prompts.analyze_market_size_prompt(idea, industry, location, market_data)
    
    try:
        res = call_gemini(analysis_prompt)
        # Use robust extractor
        data = extract_json_from_text(res.text)
        if data: return data
        
        # Fallback if extraction fails
        logger.warning("   ⚠️ JSON Extraction returned None. Using raw text fallback logic or error.")
        return None
    except Exception as e:
        logger.warning(f"   ⚠️ Sizing Analysis Error: {e}")
        return None

def plot_market_funnel(result, industry):
    try:
        # Convert strings like "$5 Billion" to relative numbers for plotting
        # (This is a visual approximation)
        raw_som = str(result.get('som_value', 'N/A'))
        clean_som = raw_som.replace('$', '').split(' ')[0]  # Grab just the number part
        
        # --- 2. UPDATE THE LABELS LIST ---
        sizes = [100, 20, 1] 
        # Use 'clean_som' (or the original if you prefer) in the label below:
        labels = [
            f"TAM\n{result.get('tam_value')}", 
            f"SAM\n{result.get('sam_value')}", 
            f"SOM\n{result.get('som_value')}" # You can change this to f"SOM\n${clean_som}M" if you want strictly formatted text
        ]
        
        colors = ['#ff9999', '#66b3ff', '#99ff99']
        
        plt.figure(figsize=(8, 6), facecolor='#F0EADC')
        ax = plt.gca()
        ax.set_facecolor('#F0EADC')
        # Create a funnel-like bar chart
        plt.barh([3, 2, 1], sizes, color=colors, height=0.6)
        plt.yticks([3, 2, 1], ["TAM", "SAM", "SOM"])
        plt.xlabel("Market Potential (Relative Scale)")
        plt.title(f"Market Sizing: {industry}")
        
        # Add text labels on bars
        for i, v in enumerate(sizes):
            plt.text(v/2, 3-i, labels[i], ha='center', va='center', fontweight='bold', color='black')
            
        os.makedirs("data_output", exist_ok=True)
        plt.savefig("data_output/market_sizing_funnel.png")
        plt.close()
        return "data_output/market_sizing_funnel.png"
    except Exception as e:
        logger.warning(f"⚠️ Sizing Visual Error: {e}")
        return None
