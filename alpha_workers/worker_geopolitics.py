from utils import update_alpha_signals
import asyncio
import json
import os
from datetime import datetime
from ddgs import DDGS

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIGNALS_FILE = os.path.join(ROOT_DIR, "alpha_signals.json")

# CONSERVATIVE SAFEGUARD 1: We look only for the worst, real market-moving events
# We don't want to short SPY just because someone tweeted the word "rocket" (e.g. SpaceX).
CRISIS_KEYWORDS = [
    "war declared",
    "missile strike",
    "nuclear threat",
    "massive sanctions",
    "geopolitical escalation"
]

def check_crisis_news():
    """
    Stable alternative to Twitter/X API (which is paid and prone to bans).
    Instead it queries fresh news via DDG. Speed is in minutes.
    """
    crisis_hits = 0
    recent_titles = []
    
    try:
        with DDGS() as ddgs:
            for kw in CRISIS_KEYWORDS:
                # max_results=2 ensures DDG won't ban us for spamming
                results = ddgs.news(kw, max_results=2)
                for res in results:
                    title = res.get('title', '').lower()
                    
                    # CONSERVATIVE SAFEGUARD 2: Confirmation. The news must have key dangerous words in the title.
                    dangerous_words = ["missile", "strike", "war", "sanction", "nuclear", "attack"]
                    if any(word in title for word in dangerous_words):
                        crisis_hits += 1
                        recent_titles.append(res.get('title'))
    except Exception as e:
        print(f"Error downloading DDG News: {e}")
        return None, f"API Error: {e} (Safeguard: ignored)"

    # CONSERVATIVE SAFEGUARD 3: We require confirmation from multiple queries/sources
    if crisis_hits >= 2:
        return -1.0, f"CRITICAL: Detected {crisis_hits} geopolitical threats! E.g.: {', '.join(recent_titles[:2])}"
        
    return 0.0, "Calm geopolitical situation, no fresh extreme events."

async def main():
    print(f"[{datetime.now().isoformat()}] Running worker_geopolitics.py (Geopolitical Macro Trigger)")
    
    score, reason = await asyncio.to_thread(check_crisis_news)
    
    signal = "NEUTRAL"
    if score == -1.0:
        signal = "BEARISH"
        
    # We write the result as a global macro indicator
    result = {
        "source": "geopolitics_worker",
        "ticker": "GLOBAL_MACRO",
        "signal": signal,
        "score": score,
        "confidence": abs(score) if score != 0.0 else 0.1,
        "timestamp": datetime.now().isoformat(),
        "details": reason
    }
    
    update_alpha_signals("geopolitics", "GLOBAL_MACRO", result)
    
    # CONSERVATIVE SAFEGUARD 4: Atomic write preventing JSON corruption
    f"Error writing to {SIGNALS_FILE}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
