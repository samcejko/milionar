from utils import update_alpha_signals
import asyncio
import json
import os
import io
import urllib.request
from datetime import datetime
from ddgs import DDGS
from pypdf import PdfReader

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(ROOT_DIR, "memory", "state.json")
WATCHLIST_FILE = os.path.join(ROOT_DIR, "memory", "watchlist.json")
SIGNALS_FILE = os.path.join(ROOT_DIR, "alpha_signals.json")

def get_tracked_tickers():
    """Loads tracked and held tickers from memory."""
    tickers = set()
    
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
                hwm = state.get("high_water_marks", {})
                for ticker in hwm.keys():
                    tickers.add(ticker)
        except Exception as e:
            print(f"Error reading state.json: {e}")

    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                wl = json.load(f)
                for item in wl.get("symbols", []):
                    if isinstance(item, dict) and "ticker" in item:
                        tickers.add(item["ticker"])
        except Exception as e:
            print(f"Error reading watchlist.json: {e}")
            
    return list(tickers)

def scan_pdf_for_metadata_leaks(ticker: str):
    """
    Searches for recent PDFs related to the ticker using DuckDuckGo.
    Downloads them and checks metadata for 'draft', 'confidential', etc.
    """
    query = f'"{ticker}" (earnings OR "press release" OR investor) filetype:pdf'
    
    suspicious_keywords = ["draft", "confidential", "internal", "do not distribute", "track changes", "revised"]
    found_urls = []
    
    try:
        with DDGS() as ddgs:
            # text search to get pdf urls
            results = ddgs.text(query, max_results=3)
            for res in results:
                href = res.get("href", "")
                if href.lower().endswith(".pdf"):
                    found_urls.append(href)
    except Exception as e:
        print(f"Error searching DDG for {ticker} PDFs: {e}")
        return 0.0, f"Search failed: {e}"

    if not found_urls:
        return 0.0, "NEUTRAL: No recent PDF press releases found."

    leak_found = False
    details_msg = []
    
    for url in found_urls:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                pdf_bytes = response.read()
                
            reader = PdfReader(io.BytesIO(pdf_bytes))
            meta = reader.metadata
            
            if meta:
                meta_str = str(meta).lower()
                for kw in suspicious_keywords:
                    if kw in meta_str:
                        leak_found = True
                        details_msg.append(f"Found '{kw}' in metadata of {url}")
                        
        except Exception as e:
            print(f"Failed to process PDF {url}: {e}")
            continue

    if leak_found:
        # A leaked draft/internal document is highly suspicious, could be good or bad, but definitely volatile.
        # Let's say it's BEARISH because poor corporate control often precedes bad news, or BULLISH if "acquisition".
        return -0.5, f"BEARISH: Metadata leak detected! {'; '.join(details_msg)}"
        
    return 0.0, "NEUTRAL: PDFs scanned, no metadata leaks found."

async def analyze_ticker(ticker):
    print(f"[{datetime.now().isoformat()}] Scanning PDF metadata for {ticker}...")
    score, reason = await asyncio.to_thread(scan_pdf_for_metadata_leaks, ticker)
    
    signal = "NEUTRAL"
    if score > 0:
        signal = "BULLISH"
    elif score < 0:
        signal = "BEARISH"
        
    return {
        "source": "pdf_metadata",
        "ticker": ticker,
        "signal": signal,
        "score": score,
        "confidence": abs(score) if score != 0.0 else 0.1,
        "timestamp": datetime.now().isoformat(),
        "details": reason
    }

async def main():
    print(f"[{datetime.now().isoformat()}] Running worker_pdf_metadata.py")
    tickers = get_tracked_tickers()
    if not tickers:
        tickers = ["NVDA", "TSLA"]
        
    tasks = [analyze_ticker(ticker) for ticker in tickers]
    results = await asyncio.gather(*tasks)
    
    for res in results:
        update_alpha_signals("pdf_metadata", res["ticker"], res)
        

if __name__ == "__main__":
    asyncio.run(main())
