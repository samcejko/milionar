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
log = logging.getLogger("worker_hack_alerts")

RSS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/"
]

HACK_KEYWORDS = ["hack", "hacked", "exploit", "exploited", "stolen", "drained", "compromised", "breach", "breached", "attacker"]

def check_hacks():
    """
    Polls major crypto RSS feeds for breaking news about hacks.
    """
    log.info("Skenuji krypto RSS feedy na hacky...")
    
    hits = []
    
    for feed_url in RSS_FEEDS:
        try:
            response = requests.get(feed_url, timeout=10)
            if response.status_code != 200:
                continue
                
            root = ET.fromstring(response.content)
            # RSS format: channel -> item -> title/description
            for item in root.findall(".//item")[:10]:  # Check only 10 latest
                title_elem = item.find("title")
                title = title_elem.text if title_elem is not None else ""
                
                title_lower = title.lower()
                
                if any(kw in title_lower.split() for kw in HACK_KEYWORDS):
                    # Check if it mentions specific coins
                    coins_affected = []
                    for coin in ["btc", "bitcoin", "eth", "ethereum", "sol", "solana", "usdt", "tether", "usdc", "curve", "crv", "uniswap", "uni"]:
                        if coin in title_lower.split():
                            coins_affected.append(coin.upper())
                            
                    if coins_affected:
                        hits.append(f"URGENT HACK ALERT: {title} (Affected: {','.join(coins_affected)})")
                    else:
                        hits.append(f"URGENT HACK ALERT (General): {title}")
                        
        except Exception as e:
            log.warning(f"Failed to fetch/parse {feed_url}: {e}")
            
    if hits:
        # Pustit jen nejnovější hit
        msg = " | ".join(hits[:2])
        return "BEARISH", msg
        
    return "NEUTRAL", "No hacks detected in recent RSS feeds."

async def main():
    signal, details = await asyncio.to_thread(check_hacks)
    
    result = {
        "source": "smart_contract_hacks",
        "signal": signal,
        "details": details,
        "timestamp": datetime.now().isoformat()
    }
    
    update_alpha_signal("hack_alerts", result)
    log.info(f"Hack Alerts signal updated: {signal}")

if __name__ == "__main__":
    asyncio.run(main())
