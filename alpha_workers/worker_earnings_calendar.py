import logging
import requests
import pandas as pd
from datetime import datetime
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from alpha_workers.utils import update_alpha_signal

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker_earnings")

def run():
    try:
        log.info("Fetching today's earnings calendar from Yahoo Finance...")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        }
        today = datetime.now().strftime("%Y-%m-%d")
        url = f"https://finance.yahoo.com/calendar/earnings?day={today}"
        
        res = requests.get(url, headers=headers, timeout=30)
        
        # Yahoo Finance often blocks generic requests without proper JS/Cookies,
        # but let's try the direct HTML table parse first.
        try:
            tables = pd.read_html(res.text)
            if not tables:
                return
                
            df = tables[0]
            if "Symbol" in df.columns:
                tickers = df["Symbol"].dropna().unique().tolist()
                if tickers:
                    signal = f"VOLATILITY WARNING: The following companies report Earnings today: {', '.join(tickers[:15])}. Expect massive price swings. If you buy these today, you are gambling on the earnings report."
                    update_alpha_signal("earnings_today", {"signal": signal, "tickers": tickers[:15]})
                    log.info(f"Earnings signal updated for {len(tickers)} companies.")
        except ValueError:
            # Pandas raises ValueError if no tables are found
            log.warning("No HTML tables found on Yahoo earnings page. Might be blocked or no earnings today.")
            
    except Exception as e:
        log.error(f"Earnings worker failed: {e}")

if __name__ == "__main__":
    run()
