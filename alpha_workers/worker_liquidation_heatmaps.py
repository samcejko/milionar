from utils import update_alpha_signals
import asyncio
import json
import os
from datetime import datetime
from ddgs import DDGS

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIGNALS_FILE = os.path.join(ROOT_DIR, "alpha_signals.json")

def check_liquidation_news():
    """
    Checks for news regarding massive liquidations in the crypto market.
    Massive long liquidations = BEARISH (cascade)
    Massive short liquidations = BULLISH (squeeze)
    """
    query = '(Bitcoin OR Crypto) ("liquidations" OR "short squeeze" OR "long squeeze" OR "cascade")'
    
    bearish_keywords = ["longs liquidated", "long liquidation", "bloodbath", "cascade down", "longs wiped out"]
    bullish_keywords = ["shorts liquidated", "short squeeze", "shorts wiped out", "cascade up"]
    
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
        print(f"Error searching DDG News for crypto liquidations: {e}")
        return 0.0, f"Search failed: {e}"

    if bearish_hits > bullish_hits and bearish_hits >= 1:
        return -0.7, f"BEARISH: Crypto long liquidation cascade detected. E.g.: {recent_titles[0]}"
    elif bullish_hits > bearish_hits and bullish_hits >= 1:
        return 0.7, f"BULLISH: Crypto short squeeze detected. E.g.: {recent_titles[0]}"
        
    return 0.0, "NEUTRAL: No major liquidation cascades detected recently."

async def main():
    print(f"[{datetime.now().isoformat()}] Running worker_liquidation_heatmaps.py (Crypto Macro)")
    
    score, reason = await asyncio.to_thread(check_liquidation_news)
    
    signal = "NEUTRAL"
    if score > 0:
        signal = "BULLISH"
    elif score < 0:
        signal = "BEARISH"
        
    result = {
        "source": "liquidation_heatmaps",
        "ticker": "CRYPTO_MACRO",
        "signal": signal,
        "score": score,
        "confidence": abs(score) if score != 0.0 else 0.1,
        "timestamp": datetime.now().isoformat(),
        "details": reason
    }
    
    update_alpha_signals("liquidation_heatmaps", "CRYPTO_MACRO", result)
    

if __name__ == "__main__":
    asyncio.run(main())
