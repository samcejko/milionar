"""
Reddit Sentiment Tracker (Hype Engine).

Fetches recent posts from top financial subreddits (WallStreetBets,
stocks, options, CryptoCurrency) to gauge retail sentiment.
Uses a simple keyword scoring system to determine hype level.
"""

import logging
import time
import urllib.parse
import asyncio

import aiohttp

log = logging.getLogger("milionar.sentiment")

_CACHE = {}
CACHE_TTL = 15 * 60  # 15 minutes in seconds


async def get_social_sentiment(ticker: str) -> dict:
    """
    Fetch and analyze Reddit sentiment for a ticker.

    Args:
        ticker: Symbol (e.g. 'NVDA', 'BTC').

    Returns:
        Dict with mention_count, sentiment_score, hype_level, summary.
    """
    ticker = ticker.upper().strip()

    # ── Check Cache ─────────────────────────────────────────
    now = time.time()
    if ticker in _CACHE:
        cache_entry = _CACHE[ticker]
        if now - cache_entry["timestamp"] < CACHE_TTL:
            log.info(f"Using cached Reddit sentiment for {ticker}")
            return cache_entry["data"]

    # For crypto pairs like BTC/USD, just search for BTC
    search_query = ticker.split("/")[0]
    query = f"{search_query} site:reddit.com/r/WallStreetBets OR site:reddit.com/r/stocks OR site:reddit.com/r/CryptoCurrency"

    posts = []
    try:
        from ddgs import DDGS
        def fetch_ddg():
            with DDGS() as ddgs:
                return list(ddgs.text(query, timelimit="w", max_results=20))
                
        results = await asyncio.to_thread(fetch_ddg)
        
        for res in results:
            posts.append({
                "data": {
                    "title": res.get("title", ""),
                    "selftext": res.get("body", "")
                }
            })
    except Exception as e:
        log.warning(f"Reddit (via DDG) fetch failed for {ticker}: {e}")
        return {
            "ticker": ticker,
            "mention_count": 0,
            "sentiment_score": 0,
            "hype_level": "LOW",
            "summary": f"Nepodařilo se načíst data přes DDG: {e}",
            "error": str(e),
        }
    
    if not posts:
        return {
            "ticker": ticker,
            "mention_count": 0,
            "sentiment_score": 0,
            "hype_level": "LOW",
            "summary": "Žádné nedávné zmínky na sledovaných subredditech.",
        }

    bull_words = {"buy", "long", "moon", "call", "bull", "calls", "rocket", "🚀"}
    bear_words = {"sell", "short", "dump", "put", "bear", "puts", "drop"}

    score = 0
    mention_count = len(posts)

    for post in posts:
        post_data = post.get("data", {})
        text = f"{post_data.get('title', '')} {post_data.get('selftext', '')}".lower()
        
        # We don't tokenize perfectly, just simple substring/word match for now
        words = set(text.split())
        
        # Bull points
        if bull_words.intersection(words) or "🚀" in text:
            score += 1
        
        # Bear points
        if bear_words.intersection(words):
            score -= 1

    if mention_count > 15:
        hype_level = "HIGH"
    elif mention_count > 5:
        hype_level = "MEDIUM"
    else:
        hype_level = "LOW"

    if score > 3:
        summary = "Extrémně pozitivní (FOMO / silný býčí sentiment)."
    elif score > 0:
        summary = "Lehce pozitivní."
    elif score < -3:
        summary = "Extrémně negativní (panika / FUD)."
    elif score < 0:
        summary = "Lehce negativní."
    else:
        summary = "Neutrální nálada."

    result = {
        "ticker": ticker,
        "mention_count": mention_count,
        "sentiment_score": score,
        "hype_level": hype_level,
        "summary": summary,
    }

    # ── Update Cache ────────────────────────────────────────
    _CACHE[ticker] = {
        "timestamp": now,
        "data": result,
    }

    return result
