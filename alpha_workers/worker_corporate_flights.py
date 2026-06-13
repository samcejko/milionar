import logging
import sys
import os
import asyncio
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from alpha_workers.utils import update_alpha_signal

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker_flights")

def check_corporate_flights():
    """
    Searches for corporate jet tracking news.
    Unusual private jet activity (e.g. CEOs flying to Omaha for Warren Buffett, 
    or flying to competitors HQ) often precedes M&A (Mergers and Acquisitions) or big partnerships.
    """
    try:
        from duckduckgo_search import DDGS
        log.info("Fetching Corporate Jet Tracking Intelligence...")
        
        query = '("corporate jet" OR "private jet" OR "flight tracker") (CEO OR executives OR merger OR acquisition OR meeting)'
        
        hits = 0
        recent_mentions = []
        
        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=5))
            for res in results:
                title = res.get("title", "").lower()
                
                # We just want any hit related to M&A flights
                if "ceo" in title or "merger" in title or "acquisition" in title or "jet" in title:
                    hits += 1
                    recent_mentions.append(res.get("title"))

        if hits >= 2:
            return "VOLATILITY_ALERT", f"CORPORATE ESPIONAGE: Unusual private jet activity detected. Possible M&A or major partnership incoming. Keep an eye on targeted companies. E.g.: {recent_mentions[0]}"
            
        return "NEUTRAL", "No unusual corporate flight activity detected."
        
    except Exception as e:
        log.error(f"Flight worker failed: {e}")
        return "ERROR", str(e)

async def main():
    signal, details = await asyncio.to_thread(check_corporate_flights)
    
    result = {
        "source": "corporate_flight_tracker",
        "signal": signal,
        "details": details,
        "timestamp": datetime.now().isoformat()
    }
    
    update_alpha_signal("corporate_flights", result)
    log.info(f"Corporate Flights signal updated: {signal}")

if __name__ == "__main__":
    asyncio.run(main())
