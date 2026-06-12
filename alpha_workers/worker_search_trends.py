from utils import update_alpha_signals
import asyncio
import json
import os
from datetime import datetime
from ddgs import DDGS

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIGNALS_FILE = os.path.join(ROOT_DIR, "alpha_signals.json")

def check_distress_trends():
    """
    Acts as a proxy for Google Trends by searching recent news for spikes in 
    distress-related topics like 'bankruptcy filings' or 'unemployment benefits'.
    """
    query = '"bankruptcy filings" OR "unemployment benefits" OR "foreclosures rising"'
    
    hits = 0
    recent_titles = []
    
    try:
        with DDGS() as ddgs:
            results = ddgs.news(query, max_results=5)
            for res in results:
                hits += 1
                recent_titles.append(res.get("title"))
                    
    except Exception as e:
        print(f"Error searching DDG News for distress trends: {e}")
        return 0.0, f"Search failed: {e}"

    if hits >= 3:
        return -0.6, f"BEARISH: Elevated news volume regarding bankruptcies/unemployment ({hits} hits). Macro distress signal. E.g.: {recent_titles[0]}"
        
    return 0.0, "NEUTRAL: Normal levels of distress-related news."

async def main():
    print(f"[{datetime.now().isoformat()}] Running worker_search_trends.py (Macro Indicator)")
    
    score, reason = await asyncio.to_thread(check_distress_trends)
    
    signal = "NEUTRAL"
    if score > 0:
        signal = "BULLISH"
    elif score < 0:
        signal = "BEARISH"
        
    result = {
        "source": "search_trends_proxy",
        "ticker": "GLOBAL_MACRO",
        "signal": signal,
        "score": score,
        "confidence": abs(score) if score != 0.0 else 0.1,
        "timestamp": datetime.now().isoformat(),
        "details": reason
    }
    
    update_alpha_signals("search_trends_proxy", "GLOBAL_MACRO", result)
    
    f"Error writing to {SIGNALS_FILE}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
