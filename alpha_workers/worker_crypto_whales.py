import logging
import sys
import os
import asyncio
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from alpha_workers.utils import update_alpha_signal

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker_crypto_whales")

RSS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/"
]

def check_crypto_whales():
    """
    Skenuje krypto RSS feedy na masivní přesuny velryb nebo tisk USDT.
    """
    log.info("Skenuji krypto RSS feedy na pohyby velryb...")
    
    bullish_hits = []
    bearish_hits = []
    
    for feed_url in RSS_FEEDS:
        try:
            response = requests.get(feed_url, timeout=10)
            if response.status_code != 200:
                continue
                
            root = ET.fromstring(response.content)
            for item in root.findall(".//item")[:10]:
                title_elem = item.find("title")
                title = title_elem.text if title_elem is not None else ""
                title_lower = title.lower()
                
                # Bullish: USDT minted or transferred from exchange
                if ("usdt" in title_lower or "tether" in title_lower or "whale" in title_lower) and ("minted" in title_lower or "accumulates" in title_lower or "buys" in title_lower or "withdraws" in title_lower):
                    bullish_hits.append(title)
                    
                # Bearish: BTC/ETH transferred to exchange (dump)
                elif ("whale" in title_lower or "btc" in title_lower or "eth" in title_lower) and ("to exchange" in title_lower or "deposits" in title_lower or "dumps" in title_lower or "sells" in title_lower):
                    bearish_hits.append(title)
                    
        except Exception as e:
            log.warning(f"Failed to fetch/parse {feed_url}: {e}")
            
    if len(bullish_hits) > len(bearish_hits) and bullish_hits:
        return "BULLISH", f"WHALE ALERT: Detekován pozitivní pohyb velryb/Tetheru. Příklad: {bullish_hits[0]}"
    elif len(bearish_hits) > len(bullish_hits) and bearish_hits:
        return "BEARISH", f"WHALE ALERT: Detekován negativní přesun na burzu (dump). Příklad: {bearish_hits[0]}"
        
    return "NEUTRAL", "No significant whale movements detected."

async def main():
    signal, details = await asyncio.to_thread(check_crypto_whales)
    
    result = {
        "source": "crypto_whale_tracker",
        "signal": signal,
        "details": details,
        "timestamp": datetime.now().isoformat()
    }
    
    update_alpha_signal("crypto_whales", result)
    log.info(f"Crypto Whales signal updated: {signal}")

if __name__ == "__main__":
    asyncio.run(main())
