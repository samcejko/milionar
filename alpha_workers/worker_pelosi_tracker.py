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

def check_congress_trades(ticker: str):
    """
    Searches DuckDuckGo News for recent mentions of the ticker being traded
    by Nancy Pelosi or other Congress members.
    """
    query = f'"{ticker}" (Pelosi OR Congress) stock'
    buy_hits = 0
    sell_hits = 0
    recent_titles = []
    
    buy_keywords = ["buy", "bought", "purchase", "purchased", "call option", "long"]
    sell_keywords = ["sell", "sold", "dump", "dumped", "put option", "short"]
    
    try:
        with DDGS() as ddgs:
            results = ddgs.news(query, max_results=5)
            for res in results:
                title = res.get('title', '').lower()
                body = res.get('body', '').lower()
                combined_text = f"{title} {body}"
                
                # Check for buy signals
                if any(word in combined_text for word in buy_keywords):
                    buy_hits += 1
                    recent_titles.append(res.get('title'))
                
                # Check for sell signals
                elif any(word in combined_text for word in sell_keywords):
                    sell_hits += 1
                    recent_titles.append(res.get('title'))
                    
    except Exception as e:
        print(f"Error searching DDG News for {ticker}: {e}")
        return 0.0, f"Search failed: {e}"

    if buy_hits > sell_hits and buy_hits >= 1:
        return 0.8, f"BULLISH: Found {buy_hits} news mentioning Congress/Pelosi buying {ticker}. E.g.: {recent_titles[0]}"
    elif sell_hits > buy_hits and sell_hits >= 1:
        return -0.8, f"BEARISH: Found {sell_hits} news mentioning Congress/Pelosi selling {ticker}. E.g.: {recent_titles[0]}"
        
    return 0.0, "NEUTRAL: No clear buying/selling by Congress detected recently."

async def analyze_ticker(ticker):
    print(f"[{datetime.now().isoformat()}] Analyzing Congress trades for {ticker}...")
    score, reason = await asyncio.to_thread(check_congress_trades, ticker)
    
    signal = "NEUTRAL"
    if score > 0:
        signal = "BULLISH"
    elif score < 0:
        signal = "BEARISH"
        
    return {
        "source": "pelosi_tracker",
        "ticker": ticker,
        "signal": signal,
        "score": score,
        "confidence": abs(score) if score != 0.0 else 0.1,
        "timestamp": datetime.now().isoformat(),
        "details": reason
    }

async def main():
    print(f"[{datetime.now().isoformat()}] Running worker_pelosi_tracker.py")
    tickers = get_tracked_tickers()
    if not tickers:
        print("Fallback: Test tickers [NVDA, TSLA, AAPL]")
        tickers = ["NVDA", "TSLA", "AAPL"]
        
    tasks = [analyze_ticker(ticker) for ticker in tickers]
    results = await asyncio.gather(*tasks)
    
    for res in results:
        update_alpha_signals("pelosi_tracker", res["ticker"], res)
        
    # Atomic write
    f"Error writing to {SIGNALS_FILE}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
