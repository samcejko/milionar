import logging
import sys
import os
import asyncio
import json
from datetime import datetime, timedelta

import pandas as pd
import pandas_ta as ta
from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker_strategy_optimizer")

def simulate_strategy(df: pd.DataFrame, sma_len: int, rsi_len: int) -> tuple[float, float]:
    df = df.copy()
    df["sma"] = ta.sma(df["close"], length=sma_len)
    df["rsi"] = ta.rsi(df["close"], length=rsi_len)
    df.dropna(inplace=True)
    
    position = 0
    entry_price = 0.0
    peak_price = 0.0
    trades = []
    wins = 0
    losses = 0

    for idx, row in df.iterrows():
        close = row["close"]
        sma = row["sma"]
        rsi = row["rsi"]

        if position > 0:
            if close > peak_price:
                peak_price = close
            
            trail_stop_hit = close < (peak_price * 0.95)
            target_hit = rsi > 70

            if trail_stop_hit or target_hit:
                profit = (close - entry_price) / entry_price
                if profit > 0: wins += 1
                else: losses += 1
                trades.append(profit)
                position = 0
        elif position == 0:
            if close > sma and rsi < 40:
                position = 1
                entry_price = close
                peak_price = close

    if position > 0:
        final_close = df.iloc[-1]["close"]
        profit = (final_close - entry_price) / entry_price
        if profit > 0: wins += 1
        else: losses += 1
        trades.append(profit)

    total = wins + losses
    if total == 0:
        return 0.0, 0.0
    win_rate = (wins / total) * 100
    avg_profit = sum(trades) / total
    return win_rate, avg_profit

async def optimize_ticker(ticker: str, is_crypto: bool, config: Config) -> dict:
    end_time = datetime.now()
    start_time = end_time - timedelta(days=180)
    
    try:
        if is_crypto:
            client = CryptoHistoricalDataClient()
            req = CryptoBarsRequest(symbol_or_symbols=ticker, timeframe=TimeFrame.Day, start=start_time, end=end_time)
            bars = client.get_crypto_bars(req)
        else:
            client = StockHistoricalDataClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY)
            req = StockBarsRequest(symbol_or_symbols=ticker, timeframe=TimeFrame.Day, start=start_time, end=end_time)
            bars = client.get_stock_bars(req)
            
        df = bars.df
        if df.empty:
            return {}
            
        if isinstance(df.index, pd.MultiIndex):
            df = df.reset_index(level=0, drop=True)
            
        best_win_rate = 0
        best_avg_profit = 0
        best_sma = 20
        best_rsi = 14
        
        # ML Grid Search Simulation
        for sma in [10, 15, 20, 30, 40, 50]:
            for rsi in [7, 10, 14, 21, 28]:
                wr, ap = simulate_strategy(df, sma, rsi)
                # Optimize for Win-Rate first, then avg_profit
                if wr > best_win_rate and ap > 0:
                    best_win_rate = wr
                    best_avg_profit = ap
                    best_sma = sma
                    best_rsi = rsi
                elif wr == best_win_rate and ap > best_avg_profit:
                    best_avg_profit = ap
                    best_sma = sma
                    best_rsi = rsi
                    
        return {
            "sma_length": best_sma,
            "rsi_length": best_rsi,
            "win_rate": best_win_rate,
            "avg_profit": best_avg_profit,
            "last_optimized": end_time.isoformat()
        }
    except Exception as e:
        log.error(f"Optimization failed for {ticker}: {e}")
        return {}

async def main():
    log.info("Starting ML Strategy Optimizer...")
    config = Config()
    
    if not config.WATCHLIST_FILE.exists():
        log.warning("No watchlist found. Nothing to optimize.")
        return
        
    try:
        with open(config.WATCHLIST_FILE, "r") as f:
            watchlist = json.load(f)
    except:
        watchlist = []
        
    optimal_params = {}
    params_file = config.MEMORY_DIR / "optimal_params.json"
    
    if params_file.exists():
        try:
            with open(params_file, "r") as f:
                optimal_params = json.load(f)
        except:
            pass
            
    for item in watchlist:
        ticker = item.get("symbol")
        is_crypto = "/" in ticker
        
        log.info(f"Optimizing parameters for {ticker}...")
        res = await optimize_ticker(ticker, is_crypto, config)
        if res and res.get("win_rate", 0) > 0:
            optimal_params[ticker] = res
            log.info(f"Found optimal params for {ticker}: SMA-{res['sma_length']}, RSI-{res['rsi_length']} (WR: {res['win_rate']}%)")
            
    with open(params_file, "w") as f:
        json.dump(optimal_params, f, indent=4)
        
    log.info("Optimization complete.")

if __name__ == "__main__":
    asyncio.run(main())
