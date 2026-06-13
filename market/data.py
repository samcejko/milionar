"""
Alpaca market data via REST API.

Direct HTTP calls to Alpaca Data API — no SDK dependency.
Supports both stocks and crypto with a simple TTL cache.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
import asyncio

import aiohttp

from config import Config

log = logging.getLogger("milionar.market")


class MarketData:
    """Fetch prices and history from Alpaca Data API (free tier)."""

    def __init__(self, config: Config):
        self.config = config
        self.headers = {
            "APCA-API-KEY-ID": config.ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": config.ALPACA_SECRET_KEY,
        }
        self.data_url = config.ALPACA_DATA_URL

        # Simple in-memory cache: {key: (data, timestamp)}
        self._cache: dict[str, tuple] = {}
        self._cache_ttl = 120  # seconds
        self.session = None

    async def get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)
        return self.session

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    # ── Public API ──────────────────────────────────────────

    async def get_price(self, ticker: str) -> dict:
        """
        Get the latest quote for a symbol.
        Detects crypto (contains '/') vs stock automatically.
        """
        ticker = ticker.upper().strip()

        if self._is_crypto(ticker):
            return await self._get_crypto_price(ticker)
        return await self._get_stock_price(ticker)

    async def get_history(self, ticker: str, days: int = 5) -> list[dict]:
        """
        Get daily OHLCV bars for a symbol.
        Returns list of dicts with date, open, high, low, close, volume.
        """
        ticker = ticker.upper().strip()
        days = max(1, min(days, 30))  # Clamp to 1-30

        if self._is_crypto(ticker):
            return await self._get_crypto_history(ticker, days)
        return await self._get_stock_history(ticker, days)

    # ── Stock data ──────────────────────────────────────────

    async def _get_stock_price(self, ticker: str) -> dict:
        """Get latest stock quote via Alpaca v2 API."""
        cache_key = f"stock_price:{ticker}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        url = f"{self.data_url}/v2/stocks/{ticker}/quotes/latest"
        data = await self._api_get(url)

        if not data or "quote" not in data:
            return {"ticker": ticker, "price": 0, "error": "No quote data"}

        q = data["quote"]
        result = {
            "ticker": ticker,
            "price": float(q.get("ap", 0) or q.get("bp", 0)),
            "ask": float(q.get("ap", 0)),
            "bid": float(q.get("bp", 0)),
            "timestamp": q.get("t", ""),
        }
        self._set_cached(cache_key, result)
        return result

    async def _get_stock_history(self, ticker: str, days: int) -> list[dict]:
        """Get stock daily bars via Alpaca v2 API."""
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days + 5)  # Extra days for weekends

        url = f"{self.data_url}/v2/stocks/{ticker}/bars"
        params = {
            "timeframe": "1Day",
            "start": start.strftime("%Y-%m-%dT00:00:00Z"),
            "end": end.strftime("%Y-%m-%dT00:00:00Z"),
            "limit": days,
            "adjustment": "split",
        }

        all_bars = []
        while True:
            data = await self._api_get(url, params)
            bars = data.get("bars", [])
            all_bars.extend(bars)
            
            page_token = data.get("next_page_token")
            if not page_token:
                break
            params["page_token"] = page_token

        return self._parse_bars(all_bars)

    # ── Crypto data ─────────────────────────────────────────

    async def _get_crypto_price(self, ticker: str) -> dict:
        """Get latest crypto quote via Alpaca v1beta3 API."""
        cache_key = f"crypto_price:{ticker}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        url = f"{self.data_url}/v1beta3/crypto/us/latest/quotes"
        # Alpaca crypto symbols use "/" separator (BTC/USD)
        params = {"symbols": ticker}
        data = await self._api_get(url, params)

        quotes = data.get("quotes", {})
        q = quotes.get(ticker, {})

        if not q:
            return {"ticker": ticker, "price": 0, "error": "No quote data"}

        result = {
            "ticker": ticker,
            "price": float(q.get("ap", 0) or q.get("bp", 0)),
            "ask": float(q.get("ap", 0)),
            "bid": float(q.get("bp", 0)),
            "timestamp": q.get("t", ""),
        }
        self._set_cached(cache_key, result)
        return result

    async def _get_crypto_history(self, ticker: str, days: int) -> list[dict]:
        """Get crypto daily bars via Alpaca v1beta3 API."""
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days + 1)

        url = f"{self.data_url}/v1beta3/crypto/us/bars"
        params = {
            "symbols": ticker,
            "timeframe": "1Day",
            "start": start.strftime("%Y-%m-%dT00:00:00Z"),
            "end": end.strftime("%Y-%m-%dT00:00:00Z"),
            "limit": days,
        }

        all_bars = []
        while True:
            data = await self._api_get(url, params)
            bars = data.get("bars", {}).get(ticker, [])
            all_bars.extend(bars)
            
            page_token = data.get("next_page_token")
            if not page_token:
                break
            params["page_token"] = page_token

        return self._parse_bars(all_bars)

    # ── News data ──────────────────────────────────────────

    async def get_alpaca_news(self, ticker: str, limit: int = 5) -> list[dict]:
        """Fetch real-time news for a ticker from Alpaca's free news API."""
        cache_key = f"news:{ticker}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        url = f"{self.data_url}/v1beta1/news"
        params = {"symbols": ticker.upper().strip(), "limit": limit}
        data = await self._api_get(url, params)

        news = data.get("news", [])
        results = []
        for n in news:
            results.append({
                "title": n.get("headline", ""),
                "snippet": n.get("summary", "")[:300],
                "url": n.get("url", ""),
                "date": n.get("created_at", ""),
                "source": n.get("source", "Alpaca"),
            })
            
        self._set_cached(cache_key, results)
        return results

    # ── Helpers ─────────────────────────────────────────────

    @staticmethod
    def _is_crypto(ticker: str) -> bool:
        """Detect crypto symbols (contain '/' like BTC/USD)."""
        return "/" in ticker

    @staticmethod
    def _parse_bars(bars: list) -> list[dict]:
        """Parse Alpaca bar objects into clean dicts."""
        return [
            {
                "date": bar.get("t", ""),
                "open": float(bar.get("o", 0)),
                "high": float(bar.get("h", 0)),
                "low": float(bar.get("l", 0)),
                "close": float(bar.get("c", 0)),
                "volume": int(bar.get("v", 0)),
            }
            for bar in (bars or [])
        ]

    async def _api_get(self, url: str, params: dict = None) -> dict:
        """Helper to fetch from Alpaca Data API with retries."""
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                session = await self.get_session()
                async with session.get(url, params=params, timeout=15) as resp:
                    if resp.status == 429:
                        log.warning(f"Data API Rate Limit (429). Retrying in 2s (Attempt {attempt+1}/{max_retries})")
                        await asyncio.sleep(2)
                        continue
                            
                    if resp.status >= 500:
                        log.warning(f"Data API Server Error ({resp.status}). Retrying in 2s (Attempt {attempt+1}/{max_retries})")
                        await asyncio.sleep(2)
                        continue
                            
                    if resp.status >= 400:
                        try:
                            error_body = await resp.json()
                            error_msg = error_body.get("message", f"HTTP {resp.status}")
                        except Exception:
                            error_text = await resp.text()
                            error_msg = f"HTTP {resp.status} - {error_text[:200]}"
                        log.error(f"Alpaca Data API error: {error_msg}")
                        return {}
                    
                    try:
                        return await resp.json()
                    except ValueError:
                        text = await resp.text()
                        log.error(f"Alpaca Data API returned invalid JSON: {text[:200]}")
                        return {}
            except aiohttp.ClientError as e:
                log.error(f"Alpaca Data API connection error: {e}")
                return {}
            except asyncio.TimeoutError:
                log.error("Alpaca Data API request timed out")
                return {}

    def _get_cached(self, key: str):
        """Return cached value if still valid, else None."""
        if key in self._cache:
            data, ts = self._cache[key]
            if time.time() - ts < self._cache_ttl:
                return data
        return None

    def _set_cached(self, key: str, data) -> None:
        """Store value in cache with current timestamp."""
        self._cache[key] = (data, time.time())
