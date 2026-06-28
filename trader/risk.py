"""
Dynamic risk management engine.

V2 (UNLEASHED): The AI is now fully responsible for position sizing,
risk management, and confidence.
This manager ONLY enforces absolute hard limits to prevent total ruin
and API crashes (buying power, duplicate positions).
"""

import logging

from config import Config

log = logging.getLogger("milionar.risk")


class RiskManager:
    """Validates trades against basic safety limits."""

    def __init__(self, config: Config):
        self.config = config

    def validate_trade(
        self,
        decision: dict,
        context: dict,
    ) -> tuple[bool, str]:
        """
        Validate a trade decision against absolute hard limits.

        Returns:
            (approved: bool, reason: str)
        """
        equity = context["portfolio"].get("equity", 0)
        positions = context.get("positions", [])
        action = decision.get("action", "HOLD")

        # -- HOLD, SELL, and ADJUST are always allowed ----------------
        if action == "HOLD":
            return True, "HOLD - no validation needed"

        if action in ["SELL", "COVER", "ADJUST"]:
            # Verify we actually hold the position
            ticker = decision.get("ticker", "")
            held = [p["symbol"] for p in positions]
            if ticker and ticker not in held:
                return False, f"Cannot {action} {ticker} - not in portfolio"
            return True, f"{action} approved"

        # -- BUY / SHORT validation ----------------------------------
        if action not in ["BUY", "SHORT"]:
            return False, f"Unknown action: {action}"

        ticker = decision.get("ticker", "UNKNOWN")

        # Extract amount proposed by AI
        amount_raw = decision.get("amount_pct", 0)
        try:
            if isinstance(amount_raw, str):
                amount_raw = amount_raw.replace("%", "").strip()
            amount_pct = float(amount_raw)
        except ValueError:
            log.warning(f"[{ticker}] Invalid amount_pct format from AI: {amount_raw}")
            amount_pct = 0.0

        if amount_pct <= 0:
            return False, f"[{ticker}] Invalid amount_pct: {amount_pct}"

        # Rule 1: No duplicate positions
        held_symbols = [p["symbol"] for p in positions]
        if ticker.upper() in held_symbols:
            return False, f"Already holding {ticker}"

        # Rule 2: Daily loss limit (total unrealized P&L)
        total_unrealized_pct = sum(
            float(p.get("unrealized_plpc", 0)) for p in positions
        )
        if total_unrealized_pct < -(self.config.DAILY_LOSS_LIMIT_PCT / 100):
            return False, (
                f"Daily loss limit breached: "
                f"{total_unrealized_pct * 100:.1f}% "
                f"(limit: -{self.config.DAILY_LOSS_LIMIT_PCT}%)"
            )

        # Rule 3: Buying Power Limits
        buying_power = context["portfolio"].get("buying_power", 0)
        notional = equity * (amount_pct / 100)

        if notional > buying_power:
            log.warning(
                f"[{ticker}] AI wants to spend ${notional:.2f} but we only have ${buying_power:.2f}. Clipping."
            )
            notional = buying_power
            # Recalculate amount_pct for logs
            amount_pct = (notional / equity) * 100 if equity > 0 else 0
            decision["amount_pct"] = round(amount_pct, 2)

        if notional < 1.0:
            return False, (
                f"[{ticker}] Notional ${notional:.2f} < $1 minimum (BP: ${buying_power:.2f})"
            )

        # Rule 4: Sanity check stop loss (AI has freedom, but let's prevent crazy numbers)
        ai_stop = decision.get("stop_loss_pct")
        if ai_stop is not None:
            ai_stop = float(ai_stop)
            # Prevent 0% or negative stop loss
            if ai_stop <= 0.0:
                log.warning(f"[{ticker}] AI stop_loss_pct {ai_stop}% invalid - setting to 1.0%")
                decision["stop_loss_pct"] = 1.0
            # Let the AI set whatever max stop loss it wants (full freedom)

        confidence = float(decision.get("confidence", 0))
        
        rr_info = ""
        if ai_stop is not None:
            rr_info = (
                f", SL={float(decision.get('stop_loss_pct', 0))}%, "
                f"TP={float(decision.get('take_profit_pct', 0))}%"
            )
            
        log.info(
            f"[OK] Trade APPROVED: {action} {ticker} {amount_pct:.2f}% "
            f"(${notional:.2f}, conf={confidence:.2f}{rr_info})"
        )
        return True, "Approved"
