import logging
import sys
import os
import asyncio
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from alpha_workers.utils import update_alpha_signal

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker_inverse_cathie")

def check_cathie_wood():
    try:
        from ddgs import DDGS
        log.info("Fetching Inverse Cathie Wood Intelligence...")
        
        query = '("Cathie Wood" OR "ARK Invest") (bought OR sold OR dumped OR buying)'
        
        bullish_hits = 0  # Inverse logic (Cathie sells = Bullish for us)
        bearish_hits = 0  # Inverse logic (Cathie buys = Bearish for us)
        recent_mentions = []
        
        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=5))
            for res in results:
                title = res.get("title", "").lower()
                body = res.get("body", "").lower()
                combined = f"{title} {body}"
                
                # If she buys, we take it as bearish
                if "bought" in combined or "buying" in combined or "added to" in combined:
                    bearish_hits += 1
                    recent_mentions.append(res.get("title"))
                    
                # If she sells, we take it as bullish
                elif "sold" in combined or "dumped" in combined or "cut stake" in combined:
                    bullish_hits += 1
                    recent_mentions.append(res.get("title"))

        if bearish_hits > bullish_hits and bearish_hits >= 2:
            return "BEARISH", f"INVERSE CATHIE ALERT: Cathie Wood is heavily BUYING. Historically, this is a top signal. E.g.: {recent_mentions[0]}"
        elif bullish_hits > bearish_hits and bullish_hits >= 2:
            return "BULLISH", f"INVERSE CATHIE ALERT: Cathie Wood is heavily SELLING/DUMPING. Historically, this is a bottom signal. E.g.: {recent_mentions[0]}"
            
        return "NEUTRAL", "No significant activity from ARK Invest detected."
        
    except Exception as e:
        log.error(f"Inverse Cathie worker failed: {e}")
        return "ERROR", str(e)

async def main():
    signal, details = await asyncio.to_thread(check_cathie_wood)
    
    result = {
        "source": "inverse_cathie",
        "signal": signal,
        "details": details,
        "timestamp": datetime.now().isoformat()
    }
    
    update_alpha_signal("inverse_cathie", result)
    log.info(f"Inverse Cathie signal updated: {signal}")

if __name__ == "__main__":
    asyncio.run(main())
