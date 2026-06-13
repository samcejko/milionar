"""
Quantitative Backtesting Engine.

Runs a rapid vector backtest over the last 180 days to give the AI a
mathematical probability (win rate) for a given ticker before buying.
"""

import logging
import asyncio
import pandas as pd
import pandas_ta as ta

log = logging.getLogger("milionar.backtest")


async def run_quantitative_backtest(ticker: str, market_data) -> dict:
    """
    Simulates a standard mean-reversion + trend following strategy
    on the last 180 days of daily data for the given ticker.
    """
    try:
        # 1. Fetch 180 days of data
        if "/" in ticker:
            bars = await market_data._get_crypto_history(ticker, days=180)
        else:
            bars = await market_data._get_stock_history(ticker, days=180)

        if len(bars) < 50:
            return {"error": "Not enough historical data to backtest (need at least 50 days)."}

        df = pd.DataFrame(bars)
        if df.empty or "close" not in df.columns:
            return {"error": "Failed to parse historical bars."}

        sma_len = 20
        rsi_len = 14
        try:
            import json
            from config import Config
            config = Config()
            params_file = config.MEMORY_DIR / "optimal_params.json"
            if params_file.exists():
                with open(params_file, "r") as f:
                    params = json.load(f)
                    if ticker in params:
                        sma_len = params[ticker].get("sma_length", 20)
                        rsi_len = params[ticker].get("rsi_length", 14)
        except:
            pass

        # 2. Calculate Indicators
        df["sma"] = ta.sma(df["close"], length=sma_len)
        df["rsi"] = ta.rsi(df["close"], length=rsi_len)
        df.dropna(inplace=True)

        # 3. Simulate Strategy (Mean Reversion in an Uptrend)
        # Entry: Close > SMA20 (uptrend) AND RSI < 40 (short-term oversold)
        # Exit: RSI > 70 (overbought) or Stop Loss 5% or Trailing Stop 5%
        
        capital = 10000.0
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

            # If holding position
            if position > 0:
                # Update peak for trailing stop
                if close > peak_price:
                    peak_price = close
                
                # Check exit conditions
                trail_stop_hit = close < (peak_price * 0.95)
                target_hit = rsi > 70

                if trail_stop_hit or target_hit:
                    # Sell
                    profit = (close - entry_price) / entry_price
                    if profit > 0:
                        wins += 1
                    else:
                        losses += 1
                    trades.append(profit)
                    position = 0
            
            # If no position
            elif position == 0:
                if close > sma and rsi < 40:
                    # Buy
                    position = 1
                    entry_price = close
                    peak_price = close

        # If still holding at the end, close it for stats
        if position > 0:
            final_close = df.iloc[-1]["close"]
            profit = (final_close - entry_price) / entry_price
            if profit > 0:
                wins += 1
            else:
                losses += 1
            trades.append(profit)

        total_trades = wins + losses
        if total_trades == 0:
            return {"status": "No trades triggered by this strategy in the last 180 days."}

        win_rate = (wins / total_trades) * 100
        avg_profit = sum(trades) / total_trades if trades else 0.0

        return {
            "strategy": f"Trend-following ML-Optimized (Buy: Price > SMA{sma_len} & RSI{rsi_len} < 40. Sell: RSI > 70 or 5% Trailing Stop)",
            "days_tested": len(df),
            "total_trades": total_trades,
            "win_rate_percent": round(win_rate, 2),
            "avg_profit_per_trade_percent": round(avg_profit * 100, 2),
            "verdict": "FAVORABLE" if win_rate >= 50 and avg_profit > 0 else "UNFAVORABLE"
        }

    except Exception as e:
        log.error(f"Backtest failed for {ticker}: {e}")
        return {"error": str(e)}
