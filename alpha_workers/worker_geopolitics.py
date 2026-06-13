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
log = logging.getLogger("worker_geopolitics")

RSS_FEEDS = [
    "http://feeds.bbci.co.uk/news/world/rss.xml",
    "https://moxie.foxnews.com/google-publisher/world.xml"
]

KEYWORDS = ["missile", "invasion", "war", "escalation", "attack", "troops", "military", "bombed", "strike"]

def check_geopolitics():
    log.info("Skenuji geopolitické RSS feedy...")
    
    hits = []
    
    for feed_url in RSS_FEEDS:
        try:
            res = requests.get(feed_url, timeout=10)
            if res.status_code != 200:
                continue
                
            root = ET.fromstring(res.content)
            for item in root.findall(".//item")[:15]:
                title = item.find("title").text if item.find("title") is not None else ""
                title_lower = title.lower()
                
                matches = sum(1 for kw in KEYWORDS if kw in title_lower.split())
                if matches >= 2: # Need at least 2 keywords in the same title to prevent false positives
                    hits.append(title)
                    
        except Exception as e:
            log.warning(f"Failed to fetch {feed_url}: {e}")
            
    if hits:
        return "BEARISH", f"GEOPOLITICAL ESCALATION DETECTED! Akcie půjdou dolů, zlato/ropa nahoru. Zprávy: {hits[0]}"
        
    return "NEUTRAL", "Geopolitická situace je klidná."

async def main():
    signal, details = await asyncio.to_thread(check_geopolitics)
    result = {
        "source": "geopolitics",
        "signal": signal,
        "details": details,
        "timestamp": datetime.now().isoformat()
    }
    update_alpha_signal("geopolitics", result)
    log.info(f"Geopolitics signal updated: {signal}")

if __name__ == "__main__":
    asyncio.run(main())
