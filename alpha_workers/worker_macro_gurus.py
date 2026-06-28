import logging
import sys
import os
import asyncio
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from alpha_workers.utils import update_alpha_signal

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker_macro_gurus")

def check_macro_gurus():
    try:
        from ddgs import DDGS
        log.info("Fetching Macro Gurus (Burry/Marks) Intelligence...")
        
        query = '("Michael Burry" OR "Howard Marks") (short OR bubble OR crash OR warning)'
        
        hits = 0
        recent_mentions = []
        
        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=5))
            for res in results:
                title = res.get("title", "").lower()
                body = res.get("body", "").lower()
                combined = f"{title} {body}"
                
                if "short" in combined or "bubble" in combined or "crash" in combined or "warn" in combined:
                    hits += 1
                    recent_mentions.append(res.get("title"))

        if hits >= 2:
            return "BEARISH", f"MACRO GURU WARNING: Michael Burry or Howard Marks are warning about a bubble or market crash. E.g.: {recent_mentions[0]}"
            
        return "NEUTRAL", "No significant warnings from Macro Gurus detected."
        
    except Exception as e:
        log.error(f"Macro Gurus worker failed: {e}")
        return "ERROR", str(e)

async def main():
    signal, details = await asyncio.to_thread(check_macro_gurus)
    
    result = {
        "source": "macro_gurus",
        "signal": signal,
        "details": details,
        "timestamp": datetime.now().isoformat()
    }
    
    update_alpha_signal("macro_gurus", result)
    log.info(f"Macro Gurus signal updated: {signal}")

if __name__ == "__main__":
    asyncio.run(main())
