from utils import update_alpha_signals
import asyncio
import json
import os
import re
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from ddgs import DDGS

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(ROOT_DIR, "memory", "state.json")
WATCHLIST_FILE = os.path.join(ROOT_DIR, "memory", "watchlist.json")
SIGNALS_FILE = os.path.join(ROOT_DIR, "alpha_signals.json")

def get_tracked_tickers():
    """Loads tracked and held tickers from memory."""
    tickers = set()
    
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
                hwm = state.get("high_water_marks", {})
                for ticker in hwm.keys():
                    tickers.add(ticker)
        except Exception as e:
            print(f"Error reading state.json: {e}")

    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                wl = json.load(f)
                for item in wl.get("symbols", []):
                    if isinstance(item, dict) and "ticker" in item:
                        tickers.add(item["ticker"])
        except Exception as e:
            print(f"Error reading watchlist.json: {e}")
            
    return list(tickers)

def get_company_name(ticker):
    """Gets full company name using Yahoo Finance API."""
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={ticker}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            quotes = data.get("quotes", [])
            if quotes:
                name = quotes[0].get("shortname") or quotes[0].get("longname")
                if name:
                    return name
    except Exception as e:
        print(f"Error getting company name for {ticker}: {e}")
    return ticker

def get_glassdoor_rating(company_name):
    """
    Conservative and stable Glassdoor rating scraping via DuckDuckGo.
    No risk of ban from LinkedIn/Glassdoor API.
    """
    try:
        with DDGS() as ddgs:
            results = ddgs.text(f"site:glassdoor.com {company_name} Reviews", max_results=4)
            for res in results:
                body = res.get('body', '')
                title = res.get('title', '')
                
                # Regex patterns for Glassdoor rating snippets e.g. "rating of 4.2 out of 5"
                match = re.search(r'(\d\.\d)\s*(?:out of 5|â˜…|stars)', body, re.IGNORECASE)
                if not match:
                    match = re.search(r'Rating:?\s*(\d\.\d)', body, re.IGNORECASE)
                if not match:
                    match = re.search(r'(\d\.\d)\s*(?:out of 5|â˜…|stars)', title, re.IGNORECASE)
                
                if match:
                    rating = float(match.group(1))
                    if 1.0 <= rating <= 5.0:
                        return rating, f"DDG Extraction successful: Rating {rating}/5 found."
    except Exception as e:
        return None, f"Glassdoor search failed: {e}"
    
    return None, "Failed to find credible Glassdoor rating."

async def analyze_ticker(ticker):
    print(f"[{datetime.now().isoformat()}] Analyzing Glassdoor rating for {ticker}...")
    name = await asyncio.to_thread(get_company_name, ticker)
    rating, reason = await asyncio.to_thread(get_glassdoor_rating, name)
    
    # -- CONSERVATIVE SAFEGUARDS -----------------------------------
    signal = "NEUTRAL"
    score = 0.0
    
    # If we don't have clear numbers, return NEUTRAL (no risk)
    if rating is not None:
        if rating <= 3.3: # 3.4 is average, <3.3 is very bad (employees fleeing)
            signal = "BEARISH"
            score = -0.5 # Conservative weight, don't force -1.0 just based on Glassdoor
        elif rating >= 4.2: # Very good rating (happy to work here)
            signal = "BULLISH"
            score = 0.5
            
    details = f"Glassdoor: {reason}"
    if rating is None:
        details += " (Safeguard: Returning NEUTRAL without stable data)"
        
    return {
        "source": "hiring_glassdoor",
        "ticker": ticker,
        "signal": signal,
        "score": score,
        "confidence": abs(score) if score != 0.0 else 0.1,
        "timestamp": datetime.now().isoformat(),
        "details": details
    }

async def main():
    print(f"[{datetime.now().isoformat()}] Running worker_hiring_glassdoor.py")
    tickers = get_tracked_tickers()
    if not tickers:
        print("Fallback: Test tickers [NVDA, TSLA, INTC]")
        tickers = ["NVDA", "TSLA", "INTC"]
        
    tasks = [analyze_ticker(ticker) for ticker in tickers]
    results = await asyncio.gather(*tasks)
    
    for res in results:
        update_alpha_signals("hiring_glassdoor", res["ticker"], res)
        
    # Atomic write (Safeguard against data corruption)

if __name__ == "__main__":
    asyncio.run(main())
