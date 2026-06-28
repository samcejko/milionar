"""
Dynamic Market Scanner.

Discovers hot, trending, or highly volatile tickers across the market
instead of relying on a hardcoded watchlist. Uses free APIs.
"""

import logging
import asyncio
import aiohttp
import random

log = logging.getLogger("milionar.market")


class MarketScanner:
    """Scans the market for trending stocks and cryptos."""

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    async def fetch_yahoo_trending(self) -> list[str]:
        """Fetch trending stocks from Yahoo Finance."""
        url = "https://query1.finance.yahoo.com/v1/finance/trending/US"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=10) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
                    # Filter out indices or weird symbols (keep pure alphabetical)
                    tickers = [q["symbol"] for q in quotes if q["symbol"].isalpha()]
                    return tickers
        except Exception as e:
            log.warning(f"Failed to fetch Yahoo trending: {e}")
            return []

    async def fetch_coingecko_trending(self) -> list[str]:
        """Fetch trending cryptocurrencies from CoinGecko."""
        url = "https://api.coingecko.com/api/v3/search/trending"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=10) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    coins = data.get("coins", [])
                    # CoinGecko returns base coins (e.g. BTC). We append /USD for Alpaca format.
                    # We also ignore weird long token names, keeping it simple.
                    cryptos = []
                    for c in coins:
                        symbol = c["item"]["symbol"].upper()
                        # Simple sanity check for token names
                        if len(symbol) <= 6 and symbol.isalpha():
                            cryptos.append(f"{symbol}/USD")
                    return cryptos
        except Exception as e:
            log.warning(f"Failed to fetch CoinGecko trending: {e}")
            return []

    async def fetch_alpaca_movers(self) -> list[str]:
        """Fetch top gainers and losers from Alpaca Screener."""
        # Using raw HTTP since alpaca-py might not have async screener easily accessible
        import os
        url = "https://data.alpaca.markets/v1beta1/screener/stocks/movers"
        headers = {
            "APCA-API-KEY-ID": os.getenv("ALPACA_API_KEY", ""),
            "APCA-API-SECRET-KEY": os.getenv("ALPACA_SECRET_KEY", ""),
            "accept": "application/json"
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        gainers = [item["symbol"] for item in data.get("gainers", [])[:3]]
                        losers = [item["symbol"] for item in data.get("losers", [])[:3]]
                        return gainers + losers
                    else:
                        log.warning(f"Alpaca movers returned {resp.status}")
                        return []
        except Exception as e:
            log.warning(f"Failed to fetch Alpaca movers: {e}")
            return []

    async def get_hot_tickers(self, limit: int = 5) -> list[str]:
        """
        Aggregate trending tickers from multiple sources and return a random sample.
        Ensures a mix of stocks and crypto.
        """
        stocks_task = self.fetch_yahoo_trending()
        crypto_task = self.fetch_coingecko_trending()
        movers_task = self.fetch_alpaca_movers()

        stocks, cryptos, movers = await asyncio.gather(stocks_task, crypto_task, movers_task)

        # Ensure we don't return an empty list if APIs fail
        if not stocks and not cryptos and not movers:
            log.warning("All scanner APIs failed. Falling back to default list.")
            fallback = ["NVDA", "BTC/USD", "TSLA", "PLTR", "ETH/USD"]
            return random.sample(fallback, min(limit, len(fallback)))

        combined = list(set(stocks + cryptos + movers))
        
        # If we have less than the limit, return all we have
        if len(combined) <= limit:
            return combined

        # Ensure we prioritize movers if possible
        if movers:
            sampled_movers = movers[:min(3, len(movers))]
            remaining = [t for t in combined if t not in sampled_movers]
            sampled_others = random.sample(remaining, min(limit - len(sampled_movers), len(remaining)))
            return sampled_movers + sampled_others

        # Otherwise pick randomly to keep it fresh
        return random.sample(combined, limit)
