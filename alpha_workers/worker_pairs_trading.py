from utils import update_alpha_signals
import asyncio
import json
import os
import urllib.request
import math
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIGNALS_FILE = os.path.join(ROOT_DIR, "alpha_signals.json")

def get_yfinance_history(ticker):
    # Fetch 1 month of 1-day interval data
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1mo"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            res = data.get("chart", {}).get("result", [])
            if res:
                closes = res[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
                # Filter out None values
                return [c for c in closes if c is not None]
    except Exception as e:
        print(f"Error fetching {ticker} history: {e}")
    return []

def check_pairs_cointegration():
    """
    Checks the spread between MSFT and AAPL. If the spread deviates by more than 2.5 standard deviations
    from the 30-day mean, it signals a pairs trade (mean reversion).
    """
    msft_closes = get_yfinance_history("MSFT")
    aapl_closes = get_yfinance_history("AAPL")
    
    if not msft_closes or not aapl_closes or len(msft_closes) != len(aapl_closes):
        return 0.0, "NEUTRAL: Missing or mismatched historical data for MSFT/AAPL."
        
    # Calculate spread MSFT/AAPL
    spreads = [m / a for m, a in zip(msft_closes, aapl_closes)]
    
    mean_spread = sum(spreads) / len(spreads)
    variance = sum((s - mean_spread) ** 2 for s in spreads) / len(spreads)
    std_dev = math.sqrt(variance)
    
    current_spread = spreads[-1]
    
    if std_dev == 0:
        return 0.0, "NEUTRAL: Zero standard deviation in spread."
        
    z_score = (current_spread - mean_spread) / std_dev
    
    if z_score > 2.5:
        return -0.8, f"BEARISH MSFT / BULLISH AAPL: Spread is {z_score:.2f} standard deviations above mean. Mean reversion expected."
    elif z_score < -2.5:
        return 0.8, f"BULLISH MSFT / BEARISH AAPL: Spread is {z_score:.2f} standard deviations below mean. Mean reversion expected."
        
    return 0.0, f"NEUTRAL: Spread is within normal range (Z-Score: {z_score:.2f})."

async def main():
    print(f"[{datetime.now().isoformat()}] Running worker_pairs_trading.py (Stat-Arb)")
    
    score, reason = await asyncio.to_thread(check_pairs_cointegration)
    
    # Positive score = MSFT undervalued relative to AAPL
    # Negative score = MSFT overvalued relative to AAPL
    
    result = {
        "source": "pairs_trading",
        "ticker": "MSFT_AAPL_SPREAD",
        "signal": "NEUTRAL" if score == 0 else ("BULLISH_SPREAD" if score > 0 else "BEARISH_SPREAD"),
        "score": score,
        "confidence": abs(score) if score != 0.0 else 0.1,
        "timestamp": datetime.now().isoformat(),
        "details": reason
    }
    
    update_alpha_signals("pairs_trading", "MSFT_AAPL_SPREAD", result)
    
    f"Error writing to {SIGNALS_FILE}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
