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

def check_token_unlocks(ticker: str):
    """
    Checks news for upcoming token unlocks for the ticker.
    Approaching unlocks are often pumped by VCs before dumping.
    """
    query = f'"{ticker}" "token unlock" (schedule OR upcoming OR cliff)'
    
    hits = 0
    recent_titles = []
    
    try:
        with DDGS() as ddgs:
            results = ddgs.news(query, max_results=3)
            for res in results:
                hits += 1
                recent_titles.append(res.get("title"))
                    
    except Exception as e:
        print(f"Error searching DDG News for {ticker} token unlock: {e}")
        return 0.0, f"Search failed: {e}"

    if hits >= 1:
        return 0.6, f"BULLISH: Upcoming token unlock detected for {ticker}. Potential pre-unlock VC pump. E.g.: {recent_titles[0]}"
        
    return 0.0, "NEUTRAL: No upcoming token unlocks detected in news."

async def analyze_ticker(ticker):
    print(f"[{datetime.now().isoformat()}] Scanning token unlocks for {ticker}...")
    score, reason = await asyncio.to_thread(check_token_unlocks, ticker)
    
    signal = "NEUTRAL"
    if score > 0:
        signal = "BULLISH"
    elif score < 0:
        signal = "BEARISH"
        
    return {
        "source": "token_unlocks",
        "ticker": ticker,
        "signal": signal,
        "score": score,
        "confidence": abs(score) if score != 0.0 else 0.1,
        "timestamp": datetime.now().isoformat(),
        "details": reason
    }

async def main():
    print(f"[{datetime.now().isoformat()}] Running worker_token_unlocks.py")
    tickers = get_tracked_tickers()
    if not tickers:
        tickers = ["SOL", "ARB", "OP", "SUI"]
        
    tasks = [analyze_ticker(ticker) for ticker in tickers]
    results = await asyncio.gather(*tasks)
    
    for res in results:
        update_alpha_signals("token_unlocks", res["ticker"], res)
        
    f"Error writing to {SIGNALS_FILE}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
