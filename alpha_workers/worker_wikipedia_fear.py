import logging
import sys
import os
import asyncio
import requests
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from alpha_workers.utils import update_alpha_signal

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker_wikipedia_fear")

def check_wikipedia():
    try:
        keywords = ["Recession", "Hyperinflation", "Bankruptcy"]
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")
        
        headers = {"User-Agent": "MilionarBot/1.0 (samuel@example.com)"}
        
        fear_hits = []
        
        for kw in keywords:
            url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents/{kw}/daily/{start_str}/{end_str}"
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                items = data.get("items", [])
                if len(items) >= 2:
                    old_views = items[0].get("views", 1)
                    new_views = items[-1].get("views", 1)
                    
                    if old_views == 0:
                        old_views = 1
                    
                    growth = (new_views - old_views) / old_views
                    if growth > 2.0: # 200% increase
                        fear_hits.append(f"{kw} (+{int(growth*100)}%)")
                        
        if fear_hits:
            return "BEARISH", f"WIKIPEDIA FEAR INDEX: Lidé najednou masivně hledají krizová slova. Detekováno: {', '.join(fear_hits)}"
            
        return "NEUTRAL", "Wikipedia Fear Index je stabilní."
    except Exception as e:
        return "ERROR", str(e)

async def main():
    signal, details = await asyncio.to_thread(check_wikipedia)
    result = {
        "source": "wikipedia_fear",
        "signal": signal,
        "details": details,
        "timestamp": datetime.now().isoformat()
    }
    update_alpha_signal("wikipedia_fear", result)
    log.info(f"Wikipedia Fear signal updated: {signal}")

if __name__ == "__main__":
    asyncio.run(main())
