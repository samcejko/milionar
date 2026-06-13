#!/usr/bin/env python3
"""
Milionar - Autonomous AI Trading Agent
======================================

Main loop: Observe -> Think -> Act -> Reflect

Every 15 minutes, the bot:
  1. OBSERVE - gathers news, market data, portfolio state, and its own memory
  2. THINK  - sends everything to an AI model (with tool-calling) for analysis
  3. ACT    - validates the decision against risk rules and executes the trade
  4. REFLECT - writes a journal entry, checks for lessons learned

Usage:
    python main.py               # Run normally (infinite loop, 15 min interval)
    python main.py --once         # Run a single cycle and exit
    python main.py --dry-run      # Run without executing real trades
    python main.py --once --dry-run  # Single dry-run cycle (for testing)
"""

import argparse
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from rich.logging import RichHandler
import signal
import sys
import os
import json
import aiofiles
from datetime import datetime

import requests

from config import Config
from brain.mcp_client import McpToolProvider
from brain.thinker import Thinker
from brain.tools import ToolRegistry
from market.news import NewsSearch
from market.data import MarketData
from market.scanner import MarketScanner
from trader.executor import TradeExecutor
from trader.risk import RiskManager
from memory.manager import MemoryManager
from memory.state import StateManager
from brain.reflection import ReflectionEngine
from brain.technical import get_technical_analysis
from brain.sentiment import get_social_sentiment
from brain.worker_manager import AlphaWorkerManager
from ui.dashboard import print_dashboard

# -- Module-level logger -------------------------------------
log = logging.getLogger("milionar")

def _safe_float(val, default=0.0) -> float:
    return float(val) if val is not None else default


# ============================================================
#  Logging Setup
# ============================================================

def setup_logging() -> None:
    """Configure dual logging: console (INFO) + file (DEBUG)."""
    Config.ensure_dirs()

    logger = logging.getLogger("milionar")
    logger.setLevel(logging.DEBUG)

    # Force UTF-8 for Windows console
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

    # Console handler - rich formatting, INFO level
    console = RichHandler(
        rich_tracebacks=True,
        show_time=True,
        show_path=False,
        markup=True
    )
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(message)s"))

    # File handler - detailed, DEBUG level, with rotation (5MB, 3 backups)
    file_handler = RotatingFileHandler(
        Config.LOG_FILE, encoding="utf-8", maxBytes=5 * 1024 * 1024, backupCount=3
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    logger.addHandler(console)
    logger.addHandler(file_handler)


# ============================================================
#  Main Bot Class
# ============================================================

class Milionar:
    """
    The autonomous trading bot.

    Orchestrates all components (brain, market, trader, memory)
    in a continuous Observe -> Think -> Act -> Reflect loop.
    """

    def __init__(self, dry_run: bool = False):
        self.config = Config()
        self.dry_run = dry_run

        # Validate API keys
        errors = self.config.validate()
        if errors:
            for err in errors:
                log.error(f"[ERROR] Config error: {err}")
            log.error("Fix your .env file and try again.")
            sys.exit(1)

        # Initialize components
        self.thinker = Thinker(self.config)
        self.market = MarketData(self.config)
        self.scanner = MarketScanner()
        self.news = NewsSearch()
        self.executor = TradeExecutor(self.config)
        self.risk = RiskManager(self.config)
        self.memory = MemoryManager(self.config)
        self.state = StateManager(self.config)
        self.worker_manager = AlphaWorkerManager()
        self.reflection = ReflectionEngine(self.config, self.memory)

        # MCP tool provider - connected in async start()
        self.mcp_provider = McpToolProvider(self.config)
        self.tools: ToolRegistry | None = None
        
        # Alpha worker manager (internal cron)
        self.worker_manager = AlphaWorkerManager()

        # Graceful shutdown flag
        self.running = True

    # -- Signal handlers -------------------------------------

    def setup_signals(self) -> None:
        """Register signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self._shutdown_handler)
        signal.signal(signal.SIGTERM, self._shutdown_handler)

    def _shutdown_handler(self, signum, frame) -> None:
        log.info("[SHUTDOWN] Signal received - finishing current cycle...")
        self.running = False

    # ============================================================
    #  Phase 1: OBSERVE
    # ============================================================

    async def observe(self) -> dict:
        """Gather all context: news, portfolio, positions, memory."""
        log.info("[OBSERVE] Gathering data...")

        # Portfolio & positions from Alpaca
        portfolio = await self.executor.get_portfolio()
        positions = await self.executor.get_positions()
        log.info(
            f"   Portfolio: ${portfolio.get('equity', 0):.2f} equity, "
            f"${portfolio.get('cash', 0):.2f} cash, "
            f"{len(positions)} positions"
        )

        # Memory (journal, lessons, watchlist)
        recent_journal = await self.memory.get_recent_journal(days=3)
        lessons = await self.memory.get_lessons()
        watchlist = await self.memory.get_watchlist()

        # Macro context (QQQ baseline)
        log.info("   Fetching Macro Context (QQQ)...")
        try:
            macro_context = await get_technical_analysis("QQQ", self.config)
            log.info(f"   Macro Context (QQQ): {macro_context.get('summary', 'N/A')}")
        except Exception as e:
            log.error(f"   Failed to fetch macro context: {e}")
            macro_context = {}

        # Async fetch of TA and Sentiment for open positions AND watchlist
        active_tickers = {p["symbol"] for p in positions}
        for w in watchlist:
            ticker = w.get("ticker")
            if ticker:
                active_tickers.add(ticker)
                
        # Auto-Discovery: If no active tickers, scan the market for hot movers
        if not active_tickers:
            auto_picked = await self.scanner.get_hot_tickers(limit=5)
            active_tickers.update(auto_picked)
            log.info(f"Watchlist is empty. Auto-discovered trending tickers: {', '.join(auto_picked)}")

        # 3. Pre-fetch multi-timeframe TA for all active tickers = list(filter(None, active_tickers))
        active_tickers = list(filter(None, active_tickers))
        ta_data = {}
        sentiment_data = {}

        if active_tickers:
            log.info(f"   Fetching TA and Sentiment for {len(active_tickers)} tracked tickers...")

            sem = asyncio.Semaphore(5)

            async def fetch_for_ticker(t: str):
                async with sem:
                    ta = await get_technical_analysis(t, self.config)
                    sent = await get_social_sentiment(t)
                    return t, ta, sent

            results = await asyncio.gather(*[fetch_for_ticker(t) for t in active_tickers])

            for t, ta, sent in results:
                ta_data[t] = ta
                sentiment_data[t] = sent

        # Targeted Reflexion
        targeted_lessons = await self.memory.get_targeted_lessons(active_tickers)
        ticker_history = await self.memory.get_ticker_history_summary(active_tickers)

        # Alternative Alpha Data
        alpha_signals = {}
        alpha_file = "alpha_signals.json"
        if os.path.exists(alpha_file):
            try:
                async with aiofiles.open(alpha_file, mode="r", encoding="utf-8") as f:
                    content = await f.read()
                    alpha_signals = json.loads(content)
                log.info(f"   Alpha Data: Loaded from {alpha_file}")
            except Exception as e:
                log.error(f"   Alpha Data error: {e}")

        # Fetch News (DDG + Alpaca)
        log.info("   Fetching news...")
        ddg_news = await asyncio.to_thread(self.news.search_trending)
        
        alpaca_news = []
        for ticker in active_tickers:
            t_news = await self.market.get_alpaca_news(ticker, limit=2)
            alpaca_news.extend(t_news)
            
        combined_news = alpaca_news + ddg_news
        seen_titles = set()
        news = []
        for n in combined_news:
            if n["title"] not in seen_titles:
                seen_titles.add(n["title"])
                news.append(n)

        return {
            "timestamp": datetime.now().isoformat(),
            "portfolio": portfolio,
            "positions": positions,
            "news": news,
            "recent_journal": recent_journal,
            "lessons": lessons,
            "watchlist": watchlist,
            "prefetched_ta": ta_data,
            "prefetched_sentiment": sentiment_data,
            "targeted_lessons": targeted_lessons,
            "ticker_history": ticker_history,
            "state_summary": await self.state.get_summary(),
            "macro_context": macro_context,
            "alpha_signals": alpha_signals,
        }

    # ============================================================
    #  Phase 2: THINK
    # ============================================================

    async def think(self, context: dict) -> dict:
        """Send context to AI for analysis (with async tool-calling loop)."""
        log.info("[THINK] AI analysis in progress...")
        decision = await self.thinker.analyze(context, self.tools)
        log.info(f"   Decision: {decision.get('action', '?')} "
                 f"{'(' + decision.get('ticker', '') + ')' if decision.get('ticker') else ''}")
        return decision

    # ============================================================
    #  Phase 3: ACT
    # ============================================================

    async def act(self, decision: dict, context: dict) -> dict:
        """Validate decision against risk rules and execute trade."""
        log.info("[ACT] Processing decision...")

        action = decision.get("action", "HOLD")

        if action == "HOLD":
            log.info("   Decision is HOLD - no action taken.")
            return {"executed": False, "reason": "HOLD decision"}

        # -- Hard Kill-Switch: daily trade limit --------------
        if self.state.daily_limit_reached:
            count = self.state.daily_trade_count
            limit = self.config.MAX_DAILY_TRADES
            log.warning(
                f"   [KILL-SWITCH] Daily trade limit reached "
                f"({count}/{limit}) - overriding to HOLD"
            )
            self._notify(
                f"[KILL-SWITCH]\n"
                f"Daily limit of {limit} trades reached.\n"
                f"All further actions today will be HOLD."
            )
            return {
                "executed": False,
                "reason": f"Daily trade limit reached ({count}/{limit})",
                "kill_switch": True,
            }

        # Get equity for risk calculation
        equity = context["portfolio"].get("equity", 0)

        # Risk validation
        approved, reason = self.risk.validate_trade(decision, context)

        if not approved:
            log.warning(f"   [REJECTED] by risk manager: {reason}")
            return {"executed": False, "reason": reason}

        # Dry-run mode: skip actual execution
        if self.dry_run:
            log.info(f"   [DRY RUN] would execute: {action} {decision.get('ticker', '?')}")
            # Count dry-run trades too, so kill-switch works in testing
            self.state.record_trade()
            return {
                "executed": False,
                "reason": "Dry-run mode - trade not executed",
                "would_have_executed": True,
            }

        # Execute the trade
        pnl_pct = 0.0
        if action == "BUY":
            result = await self.executor.buy(
                ticker=decision["ticker"],
                amount_pct=decision.get("amount_pct", 10),
                equity=equity,
                stop_loss_pct=decision.get("stop_loss_pct"),
                take_profit_pct=decision.get("take_profit_pct"),
            )
        elif action == "SHORT":
            result = await self.executor.short(
                ticker=decision["ticker"],
                amount_pct=decision.get("amount_pct", 10),
                equity=equity,
                stop_loss_pct=decision.get("stop_loss_pct"),
                take_profit_pct=decision.get("take_profit_pct"),
            )
        elif action in ["SELL", "COVER"]:
            ticker = decision["ticker"]
            pos = next((p for p in positions if p["symbol"] == ticker), None)
            result = await self.executor.sell(ticker=ticker)  # sell() closes any open position
            if result.get("executed") and "filled_avg_price" in result and pos:
                entry = _safe_float(pos.get("avg_entry_price", 0))
                filled = _safe_float(result["filled_avg_price"])
                side = pos.get("side", "long")
                if side == "long":
                    pnl_pct = (filled - entry) / entry if entry > 0 else 0
                else:
                    pnl_pct = (entry - filled) / entry if entry > 0 else 0
            elif pos:
                pnl_pct = _safe_float(pos.get("unrealized_plpc", 0))
        else:
            return {"executed": False, "reason": f"Unknown action: {action}"}

        # Record trade in state (for kill-switch counter)
        if result.get("executed"):
            await self.state.record_trade()

            if action in ["BUY", "SHORT"]:
                sl = decision.get("stop_loss_pct")
                tp = decision.get("take_profit_pct")
                if sl is not None and tp is not None:
                    await self.state.set_custom_limits(decision["ticker"], _safe_float(sl), _safe_float(tp))

            # Clean up HWM and record PnL on sell (position no longer active)
            if action == "SELL":
                await self.state.record_realized_pnl(pnl_pct)
                await self.state.remove_position_data(decision.get("ticker", ""))

            # Send Telegram notification
            action_tag = "[BUY]" if action == "BUY" else "[SELL]"
            msg = (
                f"{action_tag} {decision.get('ticker', '?')}\n"
                f"Amount: {decision.get('amount_pct', '?')}% of portfolio\n"
                f"Confidence: {decision.get('confidence', '?')}\n"
                f"Reason: {decision.get('reasoning', 'N/A')[:200]}"
            )
            self._notify(msg)

        return result

    # ============================================================
    #  Phase 4: REFLECT
    # ============================================================

    async def reflect(self, context: dict, decision: dict, result: dict) -> None:
        """Write journal entry, check for lessons, execute stop-losses."""
        log.info("[REFLECT] Writing to memory...")

        # Write journal entry for this cycle
        await self.memory.write_journal_entry(context, decision, result)

        # Record trade in history
        if result.get("executed"):
            await self.memory.record_trade(decision, result)

        # Check positions for lesson opportunities (losses > 3%)
        for pos in context.get("positions", []):
            pnl_pct = _safe_float(pos.get("unrealized_plpc", 0))
            if pnl_pct < -0.03:
                await self.memory.write_lesson(
                    ticker=pos["symbol"],
                    situation=(
                        f"Position {pos['symbol']} at {pnl_pct * 100:.1f}% "
                        f"(entry: ${pos['avg_entry_price']:.2f}, "
                        f"now: ${pos['current_price']:.2f})"
                    ),
                    result=f"Unrealized loss of {pnl_pct * 100:.1f}%",
                    lesson=(
                        "Review entry decision. Was sentiment analysis correct? "
                        "Was I chasing hype? Check if fundamentals changed."
                    ),
                )



    # ============================================================
    #  Trailing Stop-Loss Engine
    # ============================================================

    async def _check_trailing_stops(self, context: dict) -> list[str]:
        """
        Check all positions for trailing stop-loss violations.

        This runs BEFORE the THINK phase and has ABSOLUTE PRIORITY.
        If a position's price dropped > TRAILING_STOP_PERCENT below
        its high water mark, we sell immediately - no AI involved.

        Returns list of symbols that were sold.
        """
        positions = context.get("positions", [])
        if not positions:
            return []

        # Step 1: Sync HWMs (remove entries for manually closed positions)
        await self.state.sync_position_data(positions)

        # Step 2: Update high water marks with latest prices
        await self.state.update_high_water_marks(positions)

        # Step 3: Check for trailing stop triggers
        ta_data = context.get("prefetched_ta", {})
        triggered = self.state.check_trailing_stops(
            positions, self.config.TRAILING_STOP_PERCENT, ta_data
        )

        if not triggered:
            return []

        sold_symbols = []

        for trig in triggered:
            symbol = trig["symbol"]
            price = trig["current_price"]
            hwm = trig["high_water_mark"]
            drop = trig["drop_pct"]
            active_trailing_pct = trig.get("active_trailing_pct", self.config.TRAILING_STOP_PERCENT)

            log.warning(
                f"[TRAILING STOP] Triggered for {symbol}! "
                f"Price dropped by {drop:.1f}% from high ${hwm:.2f}. (Stop level: {active_trailing_pct:.1f}%)"
            )

            if not self.dry_run:
                result = await self.executor.sell(symbol)
                if result.get("executed"):
                    pos = next((p for p in positions if p["symbol"] == symbol), None)
                    if pos:
                        if "filled_avg_price" in result:
                            entry = _safe_float(pos.get("avg_entry_price", 0))
                            filled = _safe_float(result["filled_avg_price"])
                            pnl_pct = (filled - entry) / entry if entry > 0 else _safe_float(pos.get("unrealized_plpc", 0))
                        else:
                            pnl_pct = _safe_float(pos.get("unrealized_plpc", 0))
                        await self.state.record_realized_pnl(pnl_pct)
                    await self.state.record_trade()
                    await self.state.remove_position_data(symbol)
                    sold_symbols.append(symbol)

                    self._notify(
                        f"[TRAILING STOP: {symbol}]\n"
                        f"Price ${price:.2f} dropped {drop:.1f}% below maximum ${hwm:.2f}\n"
                        f"Position automatically sold to protect profits."
                    )

                    await self.memory.write_lesson(
                        ticker=symbol,
                        situation=(
                            f"Trailing stop at ${price:.2f}, "
                            f"HWM was ${hwm:.2f}, drop {drop:.1f}%"
                        ),
                        result="Automatic trailing stop sell to protect profits",
                        lesson=(
                            "Profit was locked in by trailing stop. "
                            "Review if the exit was premature or well-timed. "
                            "Was the trailing stop percentage appropriate?"
                        ),
                    )
                else:
                    log.error(f"[ERROR] Trailing stop SELL failed for {symbol}: {result}")
            else:
                log.info(
                    f"   [DRY RUN] would trailing-stop sell {symbol} "
                    f"(${price:.2f}, {drop:.1f}% below HWM ${hwm:.2f})"
                )
                self.state.record_trade()
                sold_symbols.append(symbol)

        if sold_symbols:
            log.info(
                f"[TRAILING STOP] sold {len(sold_symbols)} position(s): "
                f"{', '.join(sold_symbols)}"
            )

        return sold_symbols

    # ============================================================
    #  Emergency Shutdown
    # ============================================================

    async def _check_total_loss_limit(self, context: dict) -> bool:
        """
        Check if total portfolio loss exceeds the emergency threshold.
        Returns True if we should STOP all trading.
        """
        portfolio = context.get("portfolio", {})
        equity = portfolio.get("equity", 0)
        initial = portfolio.get("initial_equity", equity)

        if initial <= 0:
            return False

        total_loss_pct = (equity - initial) / initial

        if total_loss_pct < -(self.config.TOTAL_LOSS_LIMIT_PCT / 100):
            log.critical(
                f"[CRITICAL] TOTAL LOSS LIMIT BREACHED: "
                f"{total_loss_pct * 100:.1f}% "
                f"(limit: -{self.config.TOTAL_LOSS_LIMIT_PCT}%)"
            )
            return True

        return False

    # ============================================================
    #  Telegram Notifications
    # ============================================================

    def _notify(self, message: str) -> None:
        """Queue a Telegram notification to be sent asynchronously."""
        asyncio.create_task(self._async_notify(message))

    async def _async_notify(self, message: str) -> None:
        token = self.config.TELEGRAM_BOT_TOKEN
        chat_id = self.config.TELEGRAM_CHAT_ID
        if not token or not chat_id:
            return
            
        import aiohttp
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, timeout=10) as resp:
                        if resp.status == 200:
                            return
            except Exception as e:
                if attempt == 2:
                    log.warning(f"Telegram notification failed after 3 attempts: {e}")
            await asyncio.sleep(5)

    # ============================================================
    #  Main Cycle
    # ============================================================

    async def run_cycle(self) -> None:
        """Execute one complete Observe -> Think -> Act -> Reflect cycle."""
        cycle_start = datetime.now()
        log.info("")
        log.info(f"{'=' * 60}")
        log.info(f"[NEW CYCLE] {cycle_start.strftime('%Y-%m-%d %H:%M:%S')}")
        log.info(f"{'=' * 60}")

        # Log state summary at cycle start
        state_info = await self.state.get_summary()
        log.info(
            f"[STATE] trades today={state_info['daily_trades']}, "
            f"last cycle={state_info['last_cycle']}, "
            f"tracking {state_info['tracked_tickers']} HWMs"
        )

        try:
            # Phase 1: Observe
            context = await self.observe()

            # Print Dashboard HUD
            print_dashboard(context, self.config.CYCLE_INTERVAL_MINUTES)

            # Emergency check: total loss limit
            if await self._check_total_loss_limit(context):
                log.critical("[EMERGENCY SHUTDOWN] Selling all positions!")
                self._notify(
                    "[EMERGENCY SHUTDOWN]\n"
                    f"Total loss exceeded {self.config.TOTAL_LOSS_LIMIT_PCT}%!\n"
                    "Selling all positions and stopping trading."
                )

                if not self.dry_run:
                    for pos in context.get("positions", []):
                        symbol = pos["symbol"]
                        result = await self.executor.sell(symbol)
                        if result.get("executed"):
                            await self.state.record_trade()
                            if "filled_avg_price" in result:
                                entry = _safe_float(pos.get("avg_entry_price", 0))
                                filled = _safe_float(result["filled_avg_price"])
                                pnl_pct = (filled - entry) / entry if entry > 0 else _safe_float(pos.get("unrealized_plpc", 0))
                            else:
                                pnl_pct = _safe_float(pos.get("unrealized_plpc", 0))
                            await self.state.record_realized_pnl(pnl_pct)
                            await self.state.remove_position_data(symbol)
                            decision = {
                                "action": "SELL",
                                "ticker": symbol,
                                "reasoning": "Emergency Shutdown: Total loss limit breached."
                            }
                            await self.memory.record_trade(decision, result)

                self.running = False
                return

            # Phase 2: Think (async - MCP tool calls)
            # But first - trailing stop-loss has ABSOLUTE PRIORITY.
            # If any position breached its trailing stop, sell it
            # immediately and skip AI analysis for those tickers.
            trailing_sold = await self._check_trailing_stops(context)
            if trailing_sold:
                context["positions"] = [p for p in context.get("positions", []) if p["symbol"] not in trailing_sold]

            # Hard Rule: Crypto Volatility Check (from pre-fetched TA)
            volatile_cryptos = []
            for ticker, ta in list(context.get("prefetched_ta", {}).items()):
                if ta.get("is_volatile"):
                    volatile_cryptos.append(ticker)
                    del context["prefetched_ta"][ticker]

            if volatile_cryptos:
                log.warning(f"[WARNING] Cryptos {', '.join(volatile_cryptos)} are extremely volatile. Excluding them from this cycle.")
                
            decision = await self.think(context)

            # Phase 3: Act (sync - goes through executor.py, not MCP)
            result = await self.act(decision, context)

            # Phase 4: Reflect
            await self.reflect(context, decision, result)

            # Persist state after every cycle
            await self.state.update_last_cycle()

            # Cycle summary
            elapsed = (datetime.now() - cycle_start).total_seconds()
            log.info(f"[SUCCESS] Cycle completed in {elapsed:.1f}s")

        except Exception as e:
            log.error(f"[ERROR] Cycle failed with error: {e}", exc_info=True)
            self._notify(f"[ERROR] Cycle error:\n{str(e)[:300]}")
            # Persist state even on failure
            try:
                await self.state.update_last_cycle()
            except Exception:
                pass

    # ============================================================
    #  Start / Stop
    # ============================================================

    async def start(self, run_once: bool = False) -> None:
        """
        Start the trading bot.

        Connects to MCP server, runs trading cycles, and manages
        the async lifecycle.

        Args:
            run_once: If True, run a single cycle and exit (for testing).
        """
        mode = "DRY-RUN" if self.dry_run else "LIVE"
        log.info(f"[START] Milionar is starting up! (mode: {mode})")
        log.info(f"Cycle interval: {self.config.CYCLE_INTERVAL_MINUTES} min")
        log.info(f"Models: {', '.join(self.config.MODELS)}")
        log.info(f"Memory: {self.config.MEMORY_DIR}")
        log.info(f"MCP toolsets: {self.config.MCP_TOOLSETS}")

        # Connect to Alpaca MCP Server (permanent connection)
        try:
            await self.mcp_provider.connect()
        except Exception as e:
            log.critical(f"[ERROR] Failed to connect to MCP server: {e}")
            log.critical("Make sure 'uvx' is installed and alpaca-mcp-server is available.")
            return

        # Initialize hybrid tool registry (MCP + local tools)
        self.tools = ToolRegistry(self.mcp_provider, self.news, self.config)

        if self.config.TELEGRAM_BOT_TOKEN:
            log.info("Telegram notifications: ENABLED")
            self._notify(f"[START] Milionar is starting up!\nMode: {mode}")
        else:
            log.info("Telegram notifications: DISABLED")

        # Start background workers (if not run_once)
        if not run_once:
            self.worker_manager.start_all()

        try:
            # Run first cycle immediately
            await self.run_cycle()

            if run_once:
                log.info("[INFO] Single cycle mode - exiting.")
                return

            log.info(
                f"[INFO] Next cycle in {self.config.CYCLE_INTERVAL_MINUTES} min. "
                f"Press Ctrl+C to stop."
            )

            # Main loop - absolute scheduling
            from datetime import timedelta
            import os
            
            alpha_file = self.config.MEMORY_DIR / "alpha_signals.json"
            last_mtime = os.path.getmtime(alpha_file) if alpha_file.exists() else 0
            
            while self.running:
                now = datetime.now()
                
                # Check for weekend reflection
                if now.weekday() == 5 and now.hour == 12 and now.minute < self.config.CYCLE_INTERVAL_MINUTES:
                    try:
                        await self.reflection.run_weekend_reflection()
                    except Exception as e:
                        log.error(f"Reflection failed: {e}")
                        
                interval = self.config.CYCLE_INTERVAL_MINUTES
                next_minute = ((now.minute // interval) + 1) * interval
                
                next_run = now.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=next_minute)
                
                # Active sleep: check every 1 second for urgent interrupts
                while self.running and datetime.now() < next_run:
                    await asyncio.sleep(1)
                    
                    current_mtime = os.path.getmtime(alpha_file) if alpha_file.exists() else 0
                    if current_mtime > last_mtime:
                        log.info("🚨 [INTERRUPT] New Alpha Signal detected! Waking up immediately.")
                        last_mtime = current_mtime
                        break
                        
                if self.running:
                    await self.run_cycle()
                    last_mtime = os.path.getmtime(alpha_file) if alpha_file.exists() else last_mtime

        finally:
            # Always disconnect MCP on exit
            await self.mcp_provider.disconnect()
            await self.executor.close()
            
            # Shutdown background workers
            await self.worker_manager.shutdown()

        log.info("[SHUTDOWN] Milionar shut down gracefully.")
        self._notify("[SHUTDOWN] Milionar has been shut down.")


# ============================================================
#  Entry Point
# ============================================================

def main() -> None:
    """Parse arguments and start the bot."""
    parser = argparse.ArgumentParser(
        description="Milionar - Autonomous AI Trading Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single cycle and exit (for testing)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without executing real trades",
    )
    args = parser.parse_args()

    # Setup
    setup_logging()

    # Create and start bot
    bot = Milionar(dry_run=args.dry_run)
    bot.setup_signals()
    asyncio.run(bot.start(run_once=args.once))


if __name__ == "__main__":
    main()
