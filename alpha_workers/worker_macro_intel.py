import logging
import traceback
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from alpha_workers.utils import update_alpha_signal

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker_macro")

def run():
    try:
        from duckduckgo_search import DDGS
        log.info("Fetching Macro Intelligence (FED/CPI/Economy)...")
        
        query = "FED interest rate decision today OR US CPI inflation data today OR stock market crash news"
        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=3))
            
        if not results:
            return

        headlines = [r.get("title", "") for r in results]
        summary = " ".join(headlines)

        signal_text = f"MACRO INTEL: Zde jsou nejčerstvější zprávy ohledně FEDu, Inflace a trhu: {summary}. Pokud zprávy naznačují paniku, pád nebo zvyšování sazeb, trh půjde dolů (zvaž SHORT)."
        
        update_alpha_signal("macro_intel", {"signal": signal_text, "source": "DDG News"})
        log.info("Macro Intel updated.")
        
    except Exception as e:
        log.error(f"Macro Intel worker failed: {e}")

if __name__ == "__main__":
    run()
