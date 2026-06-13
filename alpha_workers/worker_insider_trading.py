import logging
import traceback
import requests
import pandas as pd
import sys
import os

# Add parent directory to path to import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from alpha_workers.utils import update_alpha_signal

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker_insiders")

def run():
    try:
        log.info("Fetching OpenInsider cluster buys...")
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get("http://openinsider.com/latest-cluster-buys", headers=headers, timeout=30)
        
        tables = pd.read_html(res.text)
        if not tables:
            return
            
        # The main data table is usually the largest one or the last one
        df = tables[-1]
        
        if "Ticker" not in df.columns:
            log.warning("Ticker column not found in OpenInsider table.")
            return
            
        # Filter for recent significant buys
        recent_buys = df.head(15)
        tickers = recent_buys["Ticker"].dropna().unique().tolist()
        
        if tickers:
            signal_text = f"STRONG BULLISH SIGNAL: Multiple corporate insiders (CEOs, Directors) are heavily buying their own company stock (Cluster Buys) right now. Tickers: {', '.join(tickers[:8])}. This strongly implies they know positive news is coming."
            update_alpha_signal("insider_trading", {"signal": signal_text, "tickers": tickers[:8]})
            log.info(f"Insider signal updated for: {tickers[:8]}")
            
    except Exception as e:
        log.error(f"Insider trading worker failed: {e}")

if __name__ == "__main__":
    run()
