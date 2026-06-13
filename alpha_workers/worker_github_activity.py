import logging
import sys
import os
import asyncio
import requests
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from alpha_workers.utils import update_alpha_signal

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker_github_activity")

# Sledujeme top open-source projekty
REPOS = {
    "bitcoin/bitcoin": "BTC",
    "ethereum/go-ethereum": "ETH",
    "solana-labs/solana": "SOL",
    "cardano-foundation/cardano-node": "ADA"
}

def check_github():
    try:
        frenzy_detected = []
        
        for repo, coin in REPOS.items():
            # Use public events API to see recent pushes
            url = f"https://api.github.com/repos/{repo}/events"
            res = requests.get(url, timeout=10)
            if res.status_code != 200:
                continue
                
            events = res.json()
            push_events = [e for e in events if e.get("type") == "PushEvent"]
            
            # Pokud bylo více než 10 pushů v posledních 30 eventech, vývojáři něco zuřivě kódují
            if len(push_events) >= 10:
                frenzy_detected.append(f"{coin} ({len(push_events)} pushes in last 30 events)")
                
        if frenzy_detected:
            return "BULLISH", f"GITHUB DEVELOPER FRENZY: Zvýšená aktivita vývojářů detekována u: {', '.join(frenzy_detected)}. Bude se vydávat velký update?"
            
        return "NEUTRAL", "GitHub aktivita je průměrná."
    except Exception as e:
        return "ERROR", str(e)

async def main():
    signal, details = await asyncio.to_thread(check_github)
    result = {
        "source": "github_activity",
        "signal": signal,
        "details": details,
        "timestamp": datetime.now().isoformat()
    }
    update_alpha_signal("github_activity", result)
    log.info(f"GitHub signal updated: {signal}")

if __name__ == "__main__":
    asyncio.run(main())
