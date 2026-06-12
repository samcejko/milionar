"""
Persistent bot state - survives crashes and restarts.

Manages a state.json file that tracks:
- Daily trade count (hard kill-switch)
- Current date (for daily counter reset)
- Last cycle timestamp (diagnostic)
- High water marks per ticker (trailing stop-loss)

Uses atomic writes (write to .tmp, then rename) to prevent
corruption from power loss mid-write.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config import Config
import asyncio

log = logging.getLogger("milionar.state")

def _safe_float(val, default=0.0) -> float:
    return float(val) if val is not None else default


class StateManager:
    """
    Persistent state that survives bot restarts.

    Loads from state.json on startup, saves after every mutation.
    Automatically resets daily counters when the date changes.
    Tracks high water marks per ticker for trailing stop-loss.
    """

    def __init__(self, config: Config):
        self.config = config
        self._state_file: Path = config.STATE_FILE
        self._state: dict = self._default_state()

        # Load existing state if available
        self._load()

    # -- Public interface ------------------------------------

    @property
    def daily_trade_count(self) -> int:
        """Number of executed trades today."""
        self._check_date_rollover()
        return self._state["daily_trade_count"]

    @property
    def daily_limit_reached(self) -> bool:
        """True if the daily trade limit has been reached."""
        return self.daily_trade_count >= self.config.MAX_DAILY_TRADES

    async def record_trade(self) -> int:
        """
        Increment the daily trade counter and persist state.

        Returns the new count.
        """
        await self._check_date_rollover()
        self._state["daily_trade_count"] += 1
        self._state["last_cycle"] = datetime.now().isoformat()
        count = self._state["daily_trade_count"]
        await self._save()
        log.info(
            f"Trade recorded: {count}/{self.config.MAX_DAILY_TRADES} today"
        )
        return count

    async def update_last_cycle(self) -> None:
        """Update the last cycle timestamp (called after every cycle)."""
        self._state["last_cycle"] = datetime.now().isoformat()
        await self._save()

    async def get_summary(self) -> dict:
        """Return state summary for logging/diagnostics."""
        await self._check_date_rollover()
        hwm = self._state.get("high_water_marks", {})
        w = self._state.get("win_count", 0)
        l = self._state.get("loss_count", 0)
        t = w + l
        wr = round((w / t * 100) if t > 0 else 0, 1)
        pnl = round(self._state.get("total_realized_pnl_pct", 0.0), 2)
        
        return {
            "date": self._state["date"],
            "daily_trades": f"{self._state['daily_trade_count']}/{self.config.MAX_DAILY_TRADES}",
            "last_cycle": self._state.get("last_cycle", "never"),
            "tracked_tickers": len(hwm),
            "win_rate": f"{wr}%",
            "total_trades": t,
            "total_pnl_pct": f"{pnl}%",
        }

    # -- Analytics (Feedback Loop) ---------------------------

    async def record_realized_pnl(self, pnl_pct: float) -> None:
        """Record the outcome of a closed trade (realized PnL)."""
        if pnl_pct > 0:
            self._state["win_count"] = self._state.get("win_count", 0) + 1
        else:
            self._state["loss_count"] = self._state.get("loss_count", 0) + 1
            
        self._state["total_realized_pnl_pct"] = self._state.get("total_realized_pnl_pct", 0.0) + (pnl_pct * 100)
        await self._save()
        log.info(f"Analytics updated: PnL {pnl_pct*100:+.2f}% recorded.")

    # -- Custom Limits (AI Stop-Loss/Take-Profit) ------------

    async def set_custom_limits(self, symbol: str, stop_loss_pct: float, take_profit_pct: float) -> None:
        """Store custom SL and TP determined by AI."""
        if not symbol: return
        limits = self._state.setdefault("custom_limits", {})
        limits[symbol] = {
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
        }
        log.info(f"[LIMITS] Custom limits saved for {symbol}: SL={stop_loss_pct}%, TP={take_profit_pct}%")
        await self._save()

    def get_custom_limits(self, symbol: str) -> dict | None:
        """Get custom SL and TP for a ticker, if they exist."""
        return self._state.get("custom_limits", {}).get(symbol)

    # -- High Water Marks (trailing stop-loss) ---------------

    async def update_high_water_marks(self, positions: list[dict]) -> None:
        """
        Update high water marks from current position prices.

        For each open position, if current_price > stored HWM,
        update the mark. New positions get their first HWM set.

        Args:
            positions: List of position dicts from executor.get_positions().
                       Each must have 'symbol' and 'current_price'.
        """
        hwm = self._state.setdefault("high_water_marks", {})
        changed = False

        for pos in positions:
            symbol = pos.get("symbol", "")
            current_price = _safe_float(pos.get("current_price", 0))
            if not symbol or current_price <= 0:
                continue

            old_mark = hwm.get(symbol, 0)
            if current_price > old_mark:
                hwm[symbol] = current_price
                if old_mark > 0:
                    log.info(
                        f"[HWM] updated: {symbol} "
                        f"${old_mark:.2f} -> ${current_price:.2f}"
                    )
                else:
                    log.info(
                        f"[HWM] initialized: {symbol} = ${current_price:.2f}"
                    )
                changed = True

        if changed:
            await self._save()

    def check_trailing_stops(
        self, positions: list[dict], default_trailing_pct: float, ta_data: dict = None
    ) -> list[dict]:
        """
        Check all positions against their trailing stop levels.

        Returns a list of positions that have triggered their
        trailing stop (price dropped > trailing_pct below HWM).

        Args:
            positions: Current open positions.
            trailing_pct: e.g. 5.0 means sell if price drops 5% below HWM.

        Returns:
            List of dicts: [{"symbol": ..., "current_price": ...,
                             "high_water_mark": ..., "drop_pct": ...}]
        """
        hwm = self._state.get("high_water_marks", {})
        triggered = []

        for pos in positions:
            symbol = pos.get("symbol", "")
            current_price = _safe_float(pos.get("current_price", 0))
            mark = hwm.get(symbol, 0)

            if mark <= 0 or current_price <= 0:
                continue

            # --- Dynamic ATR-Based Chandelier Exit ---
            entry_price = _safe_float(pos.get("avg_entry_price", current_price))
            profit_pct = (current_price - entry_price) / entry_price * 100 if entry_price > 0 else 0
            
            # Base trailing stop is standard default_trailing_pct (e.g. 5%)
            stop_price = mark * (1 - (default_trailing_pct / 100))
            active_trailing_pct = default_trailing_pct

            # Shrink multiplier as profit grows (Ratchet)
            multiplier = 2.0
            if profit_pct > 15.0:
                multiplier = 1.0
            elif profit_pct > 10.0:
                multiplier = 1.5

            if ta_data and symbol in ta_data:
                atr = ta_data[symbol].get("daily", {}).get("ATR_14")
                if atr and atr > 0:
                    # Chandelier Exit: HWM - (Multiplier * ATR)
                    stop_price = mark - (multiplier * atr)
                    active_trailing_pct = ((mark - stop_price) / mark) * 100

            if current_price <= stop_price:
                triggered.append({
                    "symbol": symbol,
                    "current_price": current_price,
                    "high_water_mark": mark,
                    "drop_pct": round(((mark - current_price) / mark) * 100, 2),
                    "active_trailing_pct": round(active_trailing_pct, 2),
                })

        return triggered

    async def remove_position_data(self, symbol: str) -> None:
        """Remove HWM and custom limits for a sold/closed position."""
        hwm = self._state.get("high_water_marks", {})
        limits = self._state.get("custom_limits", {})
        changed = False
        
        if symbol in hwm:
            old = hwm.pop(symbol)
            log.info(f"[HWM] removed: {symbol} (was ${old:.2f})")
            changed = True
            
        if symbol in limits:
            limits.pop(symbol)
            log.info(f"[LIMITS] removed: {symbol}")
            changed = True
            
        if changed:
            await self._save()

    async def sync_position_data(self, positions: list[dict]) -> None:
        """
        Remove HWM and custom limit entries for tickers no longer in the portfolio.

        Handles edge cases like manual position closes outside the bot.
        """
        hwm = self._state.get("high_water_marks", {})
        limits = self._state.setdefault("custom_limits", {})
        active_symbols = {pos.get("symbol", "") for pos in positions}
        stale = [sym for sym in hwm if sym not in active_symbols]
        stale_limits = [sym for sym in limits if sym not in active_symbols]

        for sym in stale:
            old = hwm.pop(sym)
            log.info(f"[HWM] cleaned up: {sym} (was ${old:.2f}, no longer held)")

        for sym in stale_limits:
            limits.pop(sym)
            log.info(f"[LIMITS] cleaned up: {sym}")

        if stale or stale_limits:
            await self._save()

    # -- Date rollover ---------------------------------------

    async def _check_date_rollover(self) -> None:
        """Reset daily counters if the date has changed."""
        today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
        if self._state["date"] != today:
            log.info(
                f"[NEW DAY] detected ({self._state['date']} -> {today}) "
                f"- resetting daily trade counter"
            )
            self._state["date"] = today
            self._state["daily_trade_count"] = 0
            await self._save()

    # -- Persistence -----------------------------------------

    def _load(self) -> None:
        """Load state from disk. Use defaults if file missing or corrupt."""
        if not self._state_file.exists():
            log.info("[STATE] No state.json found - starting fresh")
            self._save_sync()  # Create initial file synchronously during startup
            return

        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Validate required fields
            if not isinstance(data, dict) or "date" not in data:
                raise ValueError("Invalid state format")

            self._state = {**self._default_state(), **data}
            log.info(
                f"[STATE] loaded: {self._state['daily_trade_count']} trades on "
                f"{self._state['date']}, last cycle: {self._state.get('last_cycle', 'N/A')}"
            )
        except (json.JSONDecodeError, ValueError, OSError) as e:
            log.warning(f"[WARNING] Corrupt state.json - resetting: {e}")
            self._state = self._default_state()
            self._save_sync()

    def _save_sync(self) -> None:
        """Synchronous save for startup."""
        tmp_file = self._state_file.with_suffix(".json.tmp")
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2, ensure_ascii=False)
            if self._state_file.exists():
                os.replace(tmp_file, self._state_file)
            else:
                tmp_file.rename(self._state_file)
        except OSError as e:
            log.error(f"Failed to save state: {e}")

    async def _save(self) -> None:
        """
        Atomically write state to disk via asyncio.to_thread.
        """
        await asyncio.to_thread(self._save_sync)

    @staticmethod
    def _default_state() -> dict:
        """Return a clean default state."""
        return {
            "date": datetime.now(ZoneInfo("America/New_York")).date().isoformat(),
            "daily_trade_count": 0,
            "last_cycle": None,
            "high_water_marks": {},
            "custom_limits": {},
            "win_count": 0,
            "loss_count": 0,
            "total_realized_pnl_pct": 0.0,
        }
