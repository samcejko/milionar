from utils import update_alpha_signals
import asyncio
import json
import os
import urllib.request
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIGNALS_FILE = os.path.join(ROOT_DIR, "alpha_signals.json")

def check_binance_funding():
    """
    Checks the Binance Perpetual Futures funding rate for BTCUSDT.
    High funding = longs are overleveraged (BEARISH / short opportunity).
    Negative funding = shorts are overleveraged (BULLISH / long opportunity).
    """
    url = "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT"
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            funding_rate = float(data.get("lastFundingRate", 0.0))
            
            # Typical funding is 0.0001 (0.01% per 8h).
            if funding_rate > 0.0005:  # 0.05% per 8h is very high
                return -0.8, f"BEARISH (Crypto): BTC Funding rate is extremely high ({funding_rate*100:.4f}%). Longs are overleveraged, high risk of dump."
            elif funding_rate < -0.0005:
                return 0.8, f"BULLISH (Crypto): BTC Funding rate is extremely negative ({funding_rate*100:.4f}%). Shorts are trapped, high risk of short squeeze."
            else:
                return 0.0, f"NEUTRAL (Crypto): BTC Funding rate is normal ({funding_rate*100:.4f}%)."
                
    except Exception as e:
        print(f"Error checking Binance funding rate: {e}")
        return 0.0, f"API Error: {e}"

async def main():
    print(f"[{datetime.now().isoformat()}] Running worker_funding_rate.py (Crypto Macro)")
    
    score, reason = await asyncio.to_thread(check_binance_funding)
    
    signal = "NEUTRAL"
    if score > 0:
        signal = "BULLISH"
    elif score < 0:
        signal = "BEARISH"
        
    result = {
        "source": "crypto_funding",
        "ticker": "CRYPTO_MACRO",
        "signal": signal,
        "score": score,
        "confidence": abs(score) if score != 0.0 else 0.1,
        "timestamp": datetime.now().isoformat(),
        "details": reason
    }
    
    update_alpha_signals("crypto_funding", "CRYPTO_MACRO", result)
    

if __name__ == "__main__":
    asyncio.run(main())
