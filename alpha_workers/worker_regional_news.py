from utils import update_alpha_signals
import asyncio
import json
import os
from datetime import datetime
from ddgs import DDGS

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(ROOT_DIR, "memory", "state.json")
WATCHLIST_FILE = os.path.join(ROOT_DIR, "memory", "watchlist.json")
SIGNALS_FILE = os.path.join(ROOT_DIR, "alpha_signals.json")

def get_tracked_tickers():
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

def scan_local_news(ticker: str):
    """
    Searches for local/regional news regarding the ticker (strikes, factory issues, local expansion).
    """
    query = f'"{ticker}" (factory OR plant OR local OR strike OR protest OR expansion)'
    
    bearish_keywords = ["strike", "protest", "layoff", "fire", "shutdown", "closure", "violation"]
    bullish_keywords = ["expansion", "hiring", "new plant", "investment", "subsidy", "grant"]
    
    bearish_hits = 0
    bullish_hits = 0
    recent_titles = []
    
    try:
        with DDGS() as ddgs:
            results = ddgs.news(query, max_results=5)
            for res in results:
                title = res.get("title", "").lower()
                body = res.get("body", "").lower()
                combined_text = f"{title} {body}"
                
                if any(word in combined_text for word in bearish_keywords):
                    bearish_hits += 1
                    recent_titles.append(res.get("title"))
                elif any(word in combined_text for word in bullish_keywords):
                    bullish_hits += 1
                    recent_titles.append(res.get("title"))
                    
    except Exception as e:
        print(f"Error searching DDG News for {ticker} local news: {e}")
        return 0.0, f"Search failed: {e}"

    if bearish_hits > bullish_hits and bearish_hits >= 1:
        return -0.7, f"BEARISH: Found {bearish_hits} local news articles with negative sentiment. E.g.: {recent_titles[0]}"
    elif bullish_hits > bearish_hits and bullish_hits >= 1:
        return 0.7, f"BULLISH: Found {bullish_hits} local news articles with positive sentiment. E.g.: {recent_titles[0]}"
        
    return 0.0, "NEUTRAL: No significant local/regional news detected."

async def analyze_ticker(ticker):
    print(f"[{datetime.now().isoformat()}] Scanning local news for {ticker}...")
    score, reason = await asyncio.to_thread(scan_local_news, ticker)
    
    signal = "NEUTRAL"
    if score > 0:
        signal = "BULLISH"
    elif score < 0:
        signal = "BEARISH"
        
    return {
        "source": "regional_news",
        "ticker": ticker,
        "signal": signal,
        "score": score,
        "confidence": abs(score) if score != 0.0 else 0.1,
        "timestamp": datetime.now().isoformat(),
        "details": reason
    }

async def main():
    print(f"[{datetime.now().isoformat()}] Running worker_regional_news.py")
    tickers = get_tracked_tickers()
    if not tickers:
        tickers = ["NVDA", "TSLA", "INTC"]
        
    tasks = [analyze_ticker(ticker) for ticker in tickers]
    results = await asyncio.gather(*tasks)
    
    for res in results:
        update_alpha_signals("regional_news", res["ticker"], res)
        

if __name__ == "__main__":
    asyncio.run(main())
