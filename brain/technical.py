"""
Multi-timeframe technical analysis calculator.

Fetches OHLCV bars from Alpaca Data API at two timeframes and computes
key indicators using pandas-ta:

  - Daily (long-term trend): SMA-20, RSI-14
  - 15-minute (short-term timing): RSI-14

This module exists because LLMs are unreliable at math -
we pre-compute the indicators and hand the AI a clean summary
with human-readable signal interpretations per timeframe.
"""

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
import pandas_ta as ta
import aiohttp
import asyncio

from config import Config

log = logging.getLogger("milionar.technical")


async def get_technical_analysis(ticker: str, config: Config) -> dict:
    """
    Compute multi-timeframe technical analysis for a given ticker.

    Downloads daily + 15-minute bars from Alpaca, calculates indicators,
    and returns a JSON-friendly dict with clearly separated timeframes.
    """
    ticker = ticker.upper().strip()

    # -- Weekly analysis (Macro Trend) -----------------------
    weekly = await _analyze_weekly(ticker, config)

    # -- Daily analysis --------------------------------------
    daily = await _analyze_daily(ticker, config)

    # -- 15-minute analysis ----------------------------------
    intraday = await _analyze_intraday(ticker, config)

    # -- Combined output -------------------------------------
    current_price = daily.get("current_price") or intraday.get("current_price")

    result = {
        "ticker": ticker,
        "current_price": current_price,
        "weekly": weekly,
        "daily": daily,
        "intraday_15min": intraday,
        "summary": _build_summary(weekly, daily, intraday),
    }

    # -- Crypto Volatility Check -----------------------------
    if "/" in ticker or "USD" in ticker:
        volatility = await _analyze_crypto_volatility(ticker, config)
        result["minutely_volatility_pct"] = volatility.get("minutely_volatility_pct", 0)
        result["is_volatile"] = volatility.get("is_volatile", False)
        if result["is_volatile"]:
            result["summary"] += f" | [WARNING] CRYPTO IS EXTREMELY VOLATILE (movement {result['minutely_volatility_pct']}% in the last minutes)!"

    return result


# ============================================================
#  Per-Timeframe Analyzers
# ============================================================


async def _analyze_weekly(ticker: str, config: Config) -> dict:
    """Analyze weekly bars: SMA-20 (Macro Trend)."""
    try:
        # 20 weeks is roughly 5 months. Fetch 30 weeks to be safe (210 days).
        bars = await _fetch_bars(ticker, timeframe="1Week", days=210, config=config)
    except Exception as e:
        log.error(f"Failed to fetch weekly bars for {ticker}: {e}")
        return {"error": f"Weekly data unavailable: {e}"}

    if len(bars) < 21:
        return {"error": f"Not enough weekly candles ({len(bars)}, need >=21)"}

    return await asyncio.to_thread(_calc_weekly_indicators_sync, bars)

def _calc_weekly_indicators_sync(bars: list[dict]) -> dict:
    """Synchronous worker for weekly pandas calculations."""
    df = pd.DataFrame(bars)
    df["close"] = df["close"].astype(float)
    df["SMA_20"] = ta.sma(df["close"], length=20)
    
    latest = df.iloc[-1]
    price = round(float(latest["close"]), 2)
    sma_20 = round(float(latest["SMA_20"]), 2) if pd.notna(latest["SMA_20"]) else None
    
    return {
        "current_price": price,
        "SMA_20": sma_20,
        "trend": _interpret_trend(price, sma_20),
    }

async def _analyze_daily(ticker: str, config: Config) -> dict:
    """Analyze daily bars: SMA-20, RSI-14."""
    try:
        bars = await _fetch_bars(ticker, timeframe="1Day", days=55, config=config)
    except Exception as e:
        log.error(f"Failed to fetch daily bars for {ticker}: {e}")
        return {"error": f"Daily data unavailable: {e}"}

    if len(bars) < 21:
        return {"error": f"Not enough daily candles ({len(bars)}, need >=21)"}

    return await asyncio.to_thread(_calc_daily_indicators_sync, bars, ticker, config)


def _calc_daily_indicators_sync(bars: list[dict], ticker: str, config: Config) -> dict:
    """Synchronous worker for daily pandas calculations."""
    
    # Load optimal params if available
    sma_len = 20
    rsi_len = 14
    try:
        import json
        params_file = config.MEMORY_DIR / "optimal_params.json"
        if params_file.exists():
            with open(params_file, "r") as f:
                params = json.load(f)
                if ticker in params:
                    sma_len = params[ticker].get("sma_length", 20)
                    rsi_len = params[ticker].get("rsi_length", 14)
    except:
        pass
        
    df = pd.DataFrame(bars)
    df["close"] = df["close"].astype(float)

    df[f"SMA_{sma_len}"] = ta.sma(df["close"], length=sma_len)
    df[f"RSI_{rsi_len}"] = ta.rsi(df["close"], length=rsi_len)
    df["ATR_14"] = ta.atr(df["high"], df["low"], df["close"], length=14)
    df["SMA_20_Volume"] = ta.sma(df["volume"], length=20)

    latest = df.iloc[-1]
    price = round(float(latest["close"]), 2)
    sma_val = round(float(latest[f"SMA_{sma_len}"]), 2) if pd.notna(latest[f"SMA_{sma_len}"]) else None
    rsi_val = round(float(latest[f"RSI_{rsi_len}"]), 2) if pd.notna(latest[f"RSI_{rsi_len}"]) else None
    atr_14 = round(float(latest["ATR_14"]), 4) if pd.notna(latest["ATR_14"]) else None
    
    atr_pct = round((atr_14 / price) * 100, 2) if atr_14 and price > 0 else None
    
    current_vol = float(latest["volume"])
    avg_vol = float(latest["SMA_20_Volume"]) if pd.notna(latest["SMA_20_Volume"]) else current_vol
    vol_trend = "ABOVE AVERAGE" if current_vol > avg_vol else "BELOW AVERAGE"

    return {
        "current_price": price,
        f"SMA_{sma_len}": sma_val,
        f"RSI_{rsi_len}": rsi_val,
        "ATR_14": atr_14,
        "ATR_pct": atr_pct,
        "current_volume": current_vol,
        "avg_volume_20d": avg_vol,
        "volume_trend": vol_trend,
        "volume_breakout": current_vol > avg_vol * 1.5,
        "trend": _interpret_trend(price, sma_val),
        "rsi_signal": _interpret_rsi(rsi_val),
    }


async def _analyze_intraday(ticker: str, config: Config) -> dict:
    """Analyze 15-minute bars: RSI-14 only (for entry timing)."""
    try:
        bars = await _fetch_bars(ticker, timeframe="15Min", days=3, config=config)
    except Exception as e:
        log.error(f"Failed to fetch 15min bars for {ticker}: {e}")
        return {"error": f"Intraday data unavailable: {e}"}

    if len(bars) < 16:
        return {"error": f"Not enough 15min candles ({len(bars)}, need >=16)"}

    return await asyncio.to_thread(_calc_intraday_indicators_sync, bars)


def _calc_intraday_indicators_sync(bars: list[dict]) -> dict:
    """Synchronous worker for 15-minute pandas calculations."""
    df = pd.DataFrame(bars)
    if "date" in df.columns:
        df["datetime"] = pd.to_datetime(df["date"])
        df.set_index("datetime", inplace=True)

    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["volume"] = df["volume"].astype(float)

    df["RSI_14"] = ta.rsi(df["close"], length=14)
    df["VWAP"] = ta.vwap(df["high"], df["low"], df["close"], df["volume"])

    latest = df.iloc[-1]
    price = round(float(latest["close"]), 2)
    rsi_14 = round(float(latest["RSI_14"]), 2) if pd.notna(latest["RSI_14"]) else None
    vwap = round(float(latest["VWAP"]), 2) if pd.notna(latest["VWAP"]) else None
    vwap_signal = "ABOVE VWAP (Bullish)" if (vwap and price > vwap) else ("BELOW VWAP (Bearish)" if vwap else "N/A")

    return {
        "current_price": price,
        "RSI_14": rsi_14,
        "rsi_signal": _interpret_rsi(rsi_14),
        "VWAP": vwap,
        "vwap_signal": vwap_signal,
    }


async def _analyze_crypto_volatility(ticker: str, config: Config) -> dict:
    """Analyze recent 1-minute bars to detect sudden volatility."""
    try:
        # Fetch 1Min bars for the last day, but we only need the last few
        bars = await _fetch_bars(ticker, timeframe="1Min", days=1, config=config)
    except Exception as e:
        log.error(f"Failed to fetch 1min bars for volatility check: {e}")
        return {}

    if len(bars) < 2:
        return {}

    # Get the last 10 minutes of bars (or less if not available)
    recent_bars = bars[-10:]
    if len(recent_bars) < 2:
        return {}

    start_price = recent_bars[0]["open"]
    end_price = recent_bars[-1]["close"]

    if start_price <= 0:
        return {}

    change_pct = round((end_price - start_price) / start_price * 100, 2)
    is_volatile = abs(change_pct) > 1.5

    return {
        "minutely_volatility_pct": change_pct,
        "is_volatile": is_volatile,
    }


# ============================================================
#  Signal Interpretation
# ============================================================


def _interpret_rsi(rsi: float | None) -> str:
    """Human-readable RSI interpretation."""
    if rsi is None:
        return "N/A"
    if rsi < 30:
        return f"Oversold ({rsi}) - possible bounce up"
    if rsi > 70:
        return f"Overbought ({rsi}) - possible correction down"
    return f"Neutral ({rsi})"


def _interpret_trend(price: float, sma: float | None) -> str:
    """Human-readable SMA trend interpretation."""
    if sma is None or price <= 0:
        return "N/A"
    diff_pct = round((price - sma) / sma * 100, 1)
    if price > sma:
        return f"Bullish - price {diff_pct}% above SMA-20 ({sma})"
    if price < sma:
        return f"Bearish - price {abs(diff_pct)}% below SMA-20 ({sma})"
    return f"Neutral - price at SMA-20 ({sma})"


def _build_summary(weekly: dict, daily: dict, intraday: dict) -> str:
    """Build a combined multi-timeframe summary for the LLM."""
    parts = []

    # Weekly trend
    if "error" in weekly:
        parts.append(f"Weekly (Macro): {weekly['error']}")
    else:
        parts.append(f"Weekly Macro Trend: {weekly.get('trend', 'N/A')}")

    # Daily trend
    trend = daily.get("trend", "N/A")
    if "error" in daily:
        parts.append(f"Daily: {daily['error']}")
    else:
        parts.append(f"Daily trend: {trend}")
        parts.append(f"Daily RSI: {daily.get('rsi_signal', 'N/A')}")
        if daily.get('ATR_pct') is not None:
            parts.append(f"Daily Volatility (ATR): {daily['ATR_pct']}%")
        
        vol_info = f"Volume: {daily.get('volume_trend', 'N/A')}"
        if daily.get('volume_breakout'):
            vol_info += " [BREAKOUT] (more than 1.5x average)"
        parts.append(vol_info)

    # Intraday timing
    if "error" in intraday:
        parts.append(f"15min: {intraday['error']}")
    else:
        parts.append(f"15min RSI: {intraday.get('rsi_signal', 'N/A')}")
        parts.append(f"15min VWAP: {intraday.get('vwap_signal', 'N/A')}")

    return " | ".join(parts)


# ============================================================
#  Alpaca Data API helpers
# ============================================================


async def _fetch_bars(
    ticker: str, timeframe: str, days: int, config: Config,
) -> list[dict]:
    """
    Fetch OHLCV bars from Alpaca Data API.
    """
    headers = {
        "APCA-API-KEY-ID": config.ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": config.ALPACA_SECRET_KEY,
    }
    data_url = config.ALPACA_DATA_URL

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days + 5)

    if "/" in ticker:
        return await _fetch_crypto_bars(ticker, timeframe, start, end, headers, data_url)
    return await _fetch_stock_bars(ticker, timeframe, start, end, headers, data_url)


async def _fetch_stock_bars(
    ticker: str, timeframe: str, start: datetime, end: datetime,
    headers: dict, data_url: str,
) -> list[dict]:
    """Fetch stock bars via Alpaca v2 API."""
    url = f"{data_url}/v2/stocks/{ticker}/bars"
    params = {
        "timeframe": timeframe,
        "start": start.strftime("%Y-%m-%dT00:00:00Z"),
        "end": end.strftime("%Y-%m-%dT00:00:00Z"),
        "limit": 200,
        "adjustment": "split",
        "feed": "iex",
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params, timeout=15) as resp:
            resp.raise_for_status()
            data = await resp.json()
    return _parse_bars(data.get("bars", []))


async def _fetch_crypto_bars(
    ticker: str, timeframe: str, start: datetime, end: datetime,
    headers: dict, data_url: str,
) -> list[dict]:
    """Fetch crypto bars via Alpaca v1beta3 API."""
    url = f"{data_url}/v1beta3/crypto/us/bars"
    params = {
        "symbols": ticker,
        "timeframe": timeframe,
        "start": start.strftime("%Y-%m-%dT00:00:00Z"),
        "end": end.strftime("%Y-%m-%dT00:00:00Z"),
        "limit": 200,
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params, timeout=15) as resp:
            resp.raise_for_status()
            data = await resp.json()
    
    bars = data.get("bars", {}).get(ticker, [])
    return _parse_bars(bars)


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
