import logging
import sys
import os
import asyncio
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from alpha_workers.utils import update_alpha_signal

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker_value_titans")

def check_value_titans():
    try:
        from duckduckgo_search import DDGS
        log.info("Fetching Value Titans (Buffett/Damodaran) Intelligence...")
        
        query = '("Warren Buffett" OR "Berkshire Hathaway" OR "Aswath Damodaran") (bought OR undervalued OR "13F" OR buying)'
        
        hits = 0
        recent_mentions = []
        
        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=5))
            for res in results:
                title = res.get("title", "").lower()
                body = res.get("body", "").lower()
                combined = f"{title} {body}"
                
                if "bought" in combined or "buying" in combined or "undervalued" in combined or "13f" in combined:
                    hits += 1
                    recent_mentions.append(res.get("title"))

        if hits >= 2:
            return "BULLISH", f"VALUE TITANS ALERT: Warren Buffett / Damodaran are buying or calling the market undervalued. E.g.: {recent_mentions[0]}"
            
        return "NEUTRAL", "No significant buying activity from Value Titans detected."
        
    except Exception as e:
        log.error(f"Value Titans worker failed: {e}")
        return "ERROR", str(e)

async def main():
    signal, details = await asyncio.to_thread(check_value_titans)
    
    result = {
        "source": "value_titans",
        "signal": signal,
        "details": details,
        "timestamp": datetime.now().isoformat()
    }
    
    update_alpha_signal("value_titans", result)
    log.info(f"Value Titans signal updated: {signal}")

if __name__ == "__main__":
    asyncio.run(main())
