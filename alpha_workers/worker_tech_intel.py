import logging
import traceback
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from alpha_workers.utils import update_alpha_signal

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker_tech")

def run():
    try:
        from duckduckgo_search import DDGS
        log.info("Fetching Tech Intelligence (Leaks, RAM shortages, Supply chain)...")
        
        query = "semiconductor RAM shortage OR tech product leaks OR AI chip delays OR supply chain constraints"
        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=4))
            
        if not results:
            return

        headlines = [r.get("title", "") for r in results]
        summary = " | ".join(headlines)

        signal_text = f"TECH SECTOR INTEL: {summary}. Pokud zprávy hlásí nedostatky (shortages) čipů/RAM, výrobci jako Micron nebo Nvidia mohou mít problémy s dodávkami (negativní), nebo naopak zvýší ceny (pozitivní). Nové leaky produktů mohou způsobit hype. Ber to v potaz při posuzování tech akcií."
        
        update_alpha_signal("tech_intel", {"signal": signal_text, "source": "DDG News"})
        log.info("Tech Intel updated.")
        
    except Exception as e:
        log.error(f"Tech Intel worker failed: {e}")

if __name__ == "__main__":
    run()
