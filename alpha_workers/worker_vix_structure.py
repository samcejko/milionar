from utils import update_alpha_signals
import asyncio
import json
import os
import urllib.request
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIGNALS_FILE = os.path.join(ROOT_DIR, "alpha_signals.json")

def get_yfinance_price(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            res = data.get("chart", {}).get("result", [])
            if res:
                meta = res[0].get("meta", {})
                price = meta.get("regularMarketPrice")
                return price
    except Exception as e:
        print(f"Error fetching {ticker} price: {e}")
    return None

def check_vix_structure():
    """
    Compares VIX (1-month implied volatility) and ^VIX3M (3-month implied volatility).
    If VIX > ^VIX3M, term structure is in backwardation = BEARISH MACRO (fear/crash).
    If VIX < ^VIX3M, term structure is in contango = BULLISH MACRO (normal/calm).
    """
    vix_price = get_yfinance_price("^VIX")
    vix3m_price = get_yfinance_price("^VIX3M")
    
    if vix_price is None or vix3m_price is None:
        return 0.0, "API Error: Could not fetch VIX or VIX3M prices."
        
    ratio = vix_price / vix3m_price
    
    if ratio > 1.05:
        return -0.8, f"BEARISH: VIX Term Structure in BACKWARDATION (VIX: {vix_price}, VIX3M: {vix3m_price}). High fear in market."
    elif ratio < 0.95:
        return 0.5, f"BULLISH: VIX Term Structure in CONTANGO (VIX: {vix_price}, VIX3M: {vix3m_price}). Normal calm market."
        
    return 0.0, f"NEUTRAL: VIX Term Structure is flat (VIX: {vix_price}, VIX3M: {vix3m_price})."

async def main():
    print(f"[{datetime.now().isoformat()}] Running worker_vix_structure.py (Macro Indicator)")
    
    score, reason = await asyncio.to_thread(check_vix_structure)
    
    signal = "NEUTRAL"
    if score > 0:
        signal = "BULLISH"
    elif score < 0:
        signal = "BEARISH"
        
    result = {
        "source": "vix_structure",
        "ticker": "GLOBAL_MACRO",
        "signal": signal,
        "score": score,
        "confidence": abs(score) if score != 0.0 else 0.1,
        "timestamp": datetime.now().isoformat(),
        "details": reason
    }
    
    update_alpha_signals("vix_structure", "GLOBAL_MACRO", result)
    

if __name__ == "__main__":
    asyncio.run(main())
