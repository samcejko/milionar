from utils import update_alpha_signals
import asyncio
import json
import os
from datetime import datetime
from ddgs import DDGS

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIGNALS_FILE = os.path.join(ROOT_DIR, "alpha_signals.json")

def check_luxury_market():
    """
    Checks news regarding secondary market prices for luxury goods (Rolex, cars)
    as a leading indicator of 'smart money' liquidity.
    """
    query = '(Rolex OR "luxury watch" OR Porsche) (secondary market OR used prices OR dropping OR crashing)'
    
    bearish_keywords = ["drop", "dropping", "crash", "crashing", "plummet", "fall", "falling", "slump"]
    bullish_keywords = ["rise", "rising", "soar", "soaring", "record high", "surge", "surging"]
    
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
        print(f"Error searching DDG News for luxury market: {e}")
        return 0.0, f"Search failed: {e}"

    if bearish_hits > bullish_hits and bearish_hits >= 2:
        return -0.8, f"BEARISH: Luxury secondary market showing weakness ({bearish_hits} negative hits). Smart money liquidity may be drying up. E.g.: {recent_titles[0]}"
    elif bullish_hits > bearish_hits and bullish_hits >= 2:
        return 0.5, f"BULLISH: Luxury secondary market is strong ({bullish_hits} positive hits). Liquidity is abundant. E.g.: {recent_titles[0]}"
        
    return 0.0, "NEUTRAL: Luxury secondary market trends are mixed or unclear."

async def main():
    print(f"[{datetime.now().isoformat()}] Running worker_luxury_sentiment.py (Macro Indicator)")
    
    score, reason = await asyncio.to_thread(check_luxury_market)
    
    signal = "NEUTRAL"
    if score > 0:
        signal = "BULLISH"
    elif score < 0:
        signal = "BEARISH"
        
    result = {
        "source": "luxury_sentiment",
        "ticker": "GLOBAL_MACRO",
        "signal": signal,
        "score": score,
        "confidence": abs(score) if score != 0.0 else 0.1,
        "timestamp": datetime.now().isoformat(),
        "details": reason
    }
    
    update_alpha_signals("luxury_sentiment", "GLOBAL_MACRO", result)
    

if __name__ == "__main__":
    asyncio.run(main())
