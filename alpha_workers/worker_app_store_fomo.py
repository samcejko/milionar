import logging
import sys
import os
import asyncio
import requests
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from alpha_workers.utils import update_alpha_signal

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker_app_store_fomo")

def check_app_store():
    url = "https://rss.applemarketingtools.com/api/v2/us/apps/top-free/50/apps.json"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            return "NEUTRAL", "Failed to fetch App Store data."
            
        data = res.json()
        apps = data.get("feed", {}).get("results", [])
        
        crypto_apps = ["Coinbase", "Robinhood", "Binance", "Crypto.com", "Kraken", "Trust Wallet"]
        fomo_hits = []
        
        for rank, app in enumerate(apps, 1):
            name = app.get("name", "")
            for c_app in crypto_apps:
                if c_app.lower() in name.lower():
                    fomo_hits.append(f"{name} (Rank #{rank})")
                    
        # If any crypto app is in the top 10, it's extreme FOMO
        top_10 = any("Rank #1)" in h or "Rank #2)" in h or "Rank #3)" in h or "Rank #4)" in h or "Rank #5)" in h or "Rank #6)" in h or "Rank #7)" in h or "Rank #8)" in h or "Rank #9)" in h or "Rank #10)" in h for h in fomo_hits)
        
        if top_10:
            return "BULLISH", f"RETAIL FOMO ALERT: Krypto aplikace prorazily do Top 10 v USA App Store! Přicházejí hloupé peníze. Detekováno: {', '.join(fomo_hits)}"
        elif len(fomo_hits) >= 3:
            return "BULLISH", f"Mírné FOMO: Několik krypto aplikací v Top 50. Detekováno: {', '.join(fomo_hits)}"
            
        return "NEUTRAL", "App Store nevykazuje známky retail FOMO."
    except Exception as e:
        return "ERROR", str(e)

async def main():
    signal, details = await asyncio.to_thread(check_app_store)
    result = {
        "source": "app_store_fomo",
        "signal": signal,
        "details": details,
        "timestamp": datetime.now().isoformat()
    }
    update_alpha_signal("app_store_fomo", result)
    log.info(f"App Store signal updated: {signal}")

if __name__ == "__main__":
    asyncio.run(main())
