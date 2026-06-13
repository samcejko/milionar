import logging
import sys
import os
import asyncio
import requests
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from alpha_workers.utils import update_alpha_signal

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker_wsb_sentiment")

def check_wsb():
    url = "https://www.reddit.com/r/wallstreetbets/new.json?limit=50"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MilionarBot/1.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200:
            return "NEUTRAL", f"Failed to fetch Reddit data. Status: {res.status_code}"
            
        data = res.json()
        posts = data.get("data", {}).get("children", [])
        
        tickers = {"GME": 0, "AMC": 0, "TSLA": 0, "NVDA": 0, "MSTR": 0, "PLTR": 0, "COIN": 0, "AMD": 0}
        rocket_count = 0
        
        for post in posts:
            title = post["data"].get("title", "").upper()
            rocket_count += title.count("🚀")
            
            # Simple tokenization
            words = title.replace("$", " ").split()
            for t in tickers:
                if t in words:
                    tickers[t] += 1
                    
        hottest_ticker = max(tickers, key=tickers.get)
        if tickers[hottest_ticker] >= 3 or rocket_count >= 5:
            return "BULLISH", f"WSB MÁNIE DETEKOVÁNA! Nejvíce zmiňovaný: {hottest_ticker} ({tickers[hottest_ticker]}x). Počet raketek na frontpage: {rocket_count}"
        
        return "NEUTRAL", "WSB sentiment je momentálně v klidu."
    except Exception as e:
        return "ERROR", str(e)

async def main():
    signal, details = await asyncio.to_thread(check_wsb)
    result = {
        "source": "wsb_sentiment",
        "signal": signal,
        "details": details,
        "timestamp": datetime.now().isoformat()
    }
    update_alpha_signal("wsb_sentiment", result)
    log.info(f"WSB signal updated: {signal}")

if __name__ == "__main__":
    asyncio.run(main())
