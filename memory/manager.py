"""
Persistent memory manager - journal, lessons, watchlist, trades.

All data is stored in plain Markdown (.md) and JSON files.
No database required. The bot reads its own history before each cycle
to learn from past decisions and mistakes.
"""

import json
import logging
import os
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from config import Config

log = logging.getLogger("milionar.memory")


class MemoryManager:
    """Read/write the bot's persistent memory to local MD + JSON files."""

    def __init__(self, config: Config):
        self.config = config
        self._trade_summary_cache = None
        config.ensure_dirs()

    # ============================================================
    #  JOURNAL - daily trading diary in Markdown
    # ============================================================

    async def write_journal_entry(
        self, context: dict, decision: dict, result: dict
    ) -> None:
        """Append an entry to today's journal file."""
        today = datetime.now().strftime("%Y-%m-%d")
        path = self.config.JOURNAL_DIR / f"{today}.md"

        now = datetime.now().strftime("%H:%M")
        action = decision.get("action", "HOLD")
        ticker = decision.get("ticker", "-")
        confidence = decision.get("confidence", "-")
        reasoning = decision.get("reasoning", "-")
        executed = result.get("executed", False)
        reject_reason = result.get("reason", "")

        # Create file with header if it doesn't exist yet
        if not path.exists():
            path.write_text(
                f"# 📅 Trading Journal - {today}\n\n", encoding="utf-8"
            )

        # Format news summary (top 3)
        news_items = context.get("news", [])[:3]
        news_text = "\n".join(
            f"  - {n.get('title', 'N/A')}" for n in news_items
        ) or "  - No news"

        # Format portfolio snapshot
        portfolio = context.get("portfolio", {})
        equity = portfolio.get("equity", 0)
        cash = portfolio.get("cash", 0)
        num_positions = len(context.get("positions", []))

        # Analytics snapshot
        state = context.get("state_summary", {})
        win_rate = state.get("win_rate", "0%")
        pnl_pct = state.get("total_pnl_pct", "0%")

        # Build entry
        entry = f"""
---

## [CYCLE] {now}

### [OBSERVED]
- Portfolio: ${equity:.2f} equity, ${cash:.2f} cash, {num_positions} positions
- Bot Performance: Win Rate {win_rate}, Realized PnL {pnl_pct}
- Key news:
{news_text}

### [THOUGHT]
- Decision: **{action}**{f' {ticker}' if ticker != '-' else ''}
- Confidence: {confidence}
- Reasoning: {reasoning}

### [ACTION]
- Executed: {'YES' if executed else 'NO'}
{f'- Rejection reason: {reject_reason}' if not executed and reject_reason else ''}
"""

        def _write():
            with open(path, "a", encoding="utf-8") as f:
                f.write(entry)

        await asyncio.to_thread(_write)
        log.info(f"Journal entry written -> {path.name}")

    async def get_recent_journal(self, days: int = 3) -> str:
        """
        Read journal entries from the last N days.
        Truncated to save LLM tokens.
        """
        def _read():
            entries = []
            for i in range(days):
                date_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                path = self.config.JOURNAL_DIR / f"{date_str}.md"
                if path.exists():
                    content = path.read_text(encoding="utf-8")
                    cycles = content.split("## [CYCLE]")
                    if len(cycles) > 5:
                        content = cycles[0] + "## [CYCLE]" + "## [CYCLE]".join(cycles[-4:])
                    entries.append(content)
            return "\n\n".join(entries) if entries else "No previous records."

        return await asyncio.to_thread(_read)

    # ============================================================
    #  LESSONS - what the bot learned from mistakes
    # ============================================================

    async def write_lesson(
        self,
        ticker: str,
        situation: str,
        result: str,
        lesson: str,
    ) -> None:
        """Append a new lesson to lessons.md."""
        path = self.config.LESSONS_FILE

        if not path.exists():
            path.write_text(
                "# 🧠 What I learned\n\n"
                "This file contains lessons from my mistakes and observations.\n\n",
                encoding="utf-8",
            )

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = (
            f"## Lesson - {timestamp} ({ticker})\n"
            f"**Situation:** {situation}\n"
            f"**Result:** {result}\n"
            f"**Lesson:** {lesson}\n\n"
        )

        def _write():
            with open(path, "a", encoding="utf-8") as f:
                f.write(entry)

        await asyncio.to_thread(_write)
        log.info(f"Lesson recorded for {ticker}")

    async def get_lessons(self) -> str:
        """Read all lessons. Truncated to save tokens."""
        path = self.config.LESSONS_FILE
        def _read():
            if not path.exists():
                return "No lessons yet."
            content = path.read_text(encoding="utf-8")
            lessons = content.split("## Lesson")
            if len(lessons) > 10:
                content = lessons[0] + "## Lesson" + "## Lesson".join(lessons[-9:])
            return content

        return await asyncio.to_thread(_read)

    async def get_targeted_lessons(self, tickers: list[str]) -> str:
        """Extract lessons specifically for the requested tickers."""
        path = self.config.LESSONS_FILE
        def _read():
            if not path.exists() or not tickers:
                return ""
            content = path.read_text(encoding="utf-8")
            blocks = content.split("## Lesson")
            relevant_blocks = []
            for block in blocks[1:]:
                for t in tickers:
                    if f"({t})" in block or f" {t} " in block:
                        relevant_blocks.append(f"## Lesson{block.strip()}")
                        break
            return "\n\n".join(relevant_blocks[-5:])

        return await asyncio.to_thread(_read)

    # ============================================================
    #  WATCHLIST - symbols the bot is tracking
    # ============================================================

    async def get_watchlist(self) -> list[dict]:
        """Read the current watchlist."""
        path = self.config.WATCHLIST_FILE
        def _read():
            if not path.exists():
                return []
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data.get("symbols", [])
            except (json.JSONDecodeError, KeyError):
                return []

        return await asyncio.to_thread(_read)

    async def update_watchlist(self, symbols: list[dict]) -> None:
        """
        Overwrite the watchlist with a new list of symbols.
        Each symbol: {"ticker": "NVDA", "reason": "AI hype", "added": "2026-06-09"}
        """
        data = {
            "last_updated": datetime.now().isoformat(),
            "symbols": symbols,
        }
        def _write():
            tmp_file = self.config.WATCHLIST_FILE.with_suffix(".json.tmp")
            try:
                tmp_file.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                if self.config.WATCHLIST_FILE.exists():
                    os.replace(tmp_file, self.config.WATCHLIST_FILE)
                else:
                    tmp_file.rename(self.config.WATCHLIST_FILE)
                log.info(f"Watchlist updated: {len(symbols)} symbols")
            except OSError as e:
                log.error(f"Failed to save watchlist: {e}")

        await asyncio.to_thread(_write)

    # ============================================================
    #  TRADES - complete trade history
    # ============================================================

    async def record_trade(self, decision: dict, result: dict) -> None:
        """Append a trade record to trades.jsonl."""
        path = self.config.TRADES_FILE

        def _write():
            trade_count = 0
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    trade_count = sum(1 for _ in f)

            trade = {
                "id": f"t{trade_count + 1:04d}",
                "timestamp": datetime.now().isoformat(),
                "action": decision.get("action", ""),
                "ticker": decision.get("ticker", ""),
                "amount_pct": decision.get("amount_pct", 0),
                "confidence": decision.get("confidence", 0),
                "reasoning": decision.get("reasoning", ""),
                "executed": result.get("executed", False),
                "order_id": result.get("order_id", ""),
                "notional": result.get("notional", 0),
                "status": result.get("status", ""),
            }

            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(trade, ensure_ascii=False) + "\n")
            return trade

        trade = await asyncio.to_thread(_write)

        await self._ensure_trade_cache()
        if trade["executed"] and trade["ticker"]:
            ticker = trade["ticker"]
            if ticker not in self._trade_summary_cache:
                self._trade_summary_cache[ticker] = {"trades": 0, "last_action": None, "last_date": None}
            self._trade_summary_cache[ticker]["trades"] += 1
            self._trade_summary_cache[ticker]["last_action"] = trade["action"]
            self._trade_summary_cache[ticker]["last_date"] = trade["timestamp"]

        log.info(f"Trade recorded: {trade['id']} - {trade['action']} {trade['ticker']}")

    async def get_trade_history(self, limit: int = 20) -> list[dict]:
        """Read recent trade history."""
        path = self.config.TRADES_FILE
        
        def _read():
            if not path.exists():
                return []
            trades = []
            try:
                with open(path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    for line in lines[-limit:]:
                        trades.append(json.loads(line.strip()))
                return trades
            except Exception as e:
                log.warning(f"Error reading trade history: {e}")
                return trades
                
        return await asyncio.to_thread(_read)

    async def _ensure_trade_cache(self) -> None:
        """Initialize the in-memory trade summary cache."""
        if self._trade_summary_cache is not None:
            return
            
        def _read_cache():
            self._trade_summary_cache = {}
            path = self.config.TRADES_FILE
            if not path.exists():
                return
                
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip(): continue
                        trade = json.loads(line.strip())
                        if trade.get("executed"):
                            ticker = trade.get("ticker")
                            if not ticker: continue
                            if ticker not in self._trade_summary_cache:
                                self._trade_summary_cache[ticker] = {"trades": 0, "last_action": None, "last_date": None}
                            self._trade_summary_cache[ticker]["trades"] += 1
                            self._trade_summary_cache[ticker]["last_action"] = trade.get("action")
                            self._trade_summary_cache[ticker]["last_date"] = trade.get("timestamp")
            except Exception as e:
                log.warning(f"Error initializing trade summary cache: {e}")

        await asyncio.to_thread(_read_cache)

    async def get_ticker_history_summary(self, tickers: list[str]) -> dict:
        """Get summary of past trades for specific tickers from in-memory cache."""
        if not tickers:
            return {}

        await self._ensure_trade_cache()
        summary = {}
        for t in tickers:
            if t in self._trade_summary_cache:
                # copy dict to prevent external modification
                summary[t] = dict(self._trade_summary_cache[t])
            else:
                summary[t] = {"trades": 0, "last_action": None, "last_date": None}
        return summary
