import logging
import sys
import os
import asyncio
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from alpha_workers.utils import update_alpha_signal

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker_cramer")

def check_jim_cramer():
    try:
        from ddgs import DDGS
        log.info("Fetching Jim Cramer recommendations...")
        
        query = '"Jim Cramer" (buy OR sell OR recommends OR "mad money")'
        
        bullish_hits = 0
        bearish_hits = 0
        recent_mentions = []
        
        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=8))
            for res in results:
                title = res.get("title", "").lower()
                body = res.get("body", "").lower()
                combined = f"{title} {body}"
                
                # Inverse Logic: Cramer BUY = Bearish for us
                if "buy" in combined or "bullish" in combined or "recommends" in combined:
                    bearish_hits += 1  # We inverse it
                    recent_mentions.append(res.get("title"))
                # Inverse Logic: Cramer SELL = Bullish for us
                elif "sell" in combined or "bearish" in combined or "dump" in combined:
                    bullish_hits += 1  # We inverse it
                    recent_mentions.append(res.get("title"))

        if bearish_hits > bullish_hits and bearish_hits >= 2:
            return "BEARISH", f"INVERSE CRAMER ALERT: Jim Cramer is recommending to BUY. Statistically, this is a SELL/SHORT signal. Mentions: {recent_mentions[0]}"
        elif bullish_hits > bearish_hits and bullish_hits >= 2:
            return "BULLISH", f"INVERSE CRAMER ALERT: Jim Cramer is panicking and recommending to SELL. Statistically, this is a strong BUY signal. Mentions: {recent_mentions[0]}"
            
        return "NEUTRAL", "Jim Cramer's recent mentions are mixed or absent."
        
    except Exception as e:
        log.error(f"Cramer worker failed: {e}")
        return "ERROR", str(e)

async def main():
    signal, details = await asyncio.to_thread(check_jim_cramer)
    
    result = {
        "source": "jim_cramer_inverse",
        "signal": signal,
        "details": details,
        "timestamp": datetime.now().isoformat()
    }
    
    update_alpha_signal("jim_cramer", result)
    log.info(f"Jim Cramer signal updated: {signal}")

if __name__ == "__main__":
    asyncio.run(main())
