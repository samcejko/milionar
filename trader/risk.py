"""
Dynamic risk management engine.

Scales position sizing, stop-loss levels, and max positions
dynamically based on current account equity. Small accounts
get fewer, larger positions; big accounts get more, smaller ones.

This is the LAST GATE before any trade executes - if the risk
manager says no, the trade is rejected regardless of AI confidence.
"""

import logging

from config import Config

log = logging.getLogger("milionar.risk")


# -- Dynamic scaling tiers -----------------------------------
# Each tier defines limits for accounts of that equity range.
# As the account grows, limits automatically adjust.

TIERS = [
    {
        "name": "micro",
        "max_equity": 50,
        "max_positions": 2,
        "max_per_position_pct": 45,
        "stop_loss_pct": 7,
        "min_confidence": 0.65,
    },
    {
        "name": "small",
        "max_equity": 500,
        "max_positions": 3,
        "max_per_position_pct": 33,
        "stop_loss_pct": 5,
        "min_confidence": 0.60,
    },
    {
        "name": "medium",
        "max_equity": 5_000,
        "max_positions": 5,
        "max_per_position_pct": 20,
        "stop_loss_pct": 4,
        "min_confidence": 0.60,
    },
    {
        "name": "large",
        "max_equity": 50_000,
        "max_positions": 8,
        "max_per_position_pct": 12,
        "stop_loss_pct": 3,
        "min_confidence": 0.60,
    },
    {
        "name": "whale",
        "max_equity": float("inf"),
        "max_positions": 12,
        "max_per_position_pct": 8,
        "stop_loss_pct": 2,
        "min_confidence": 0.60,
    },
]


class RiskManager:
    """Validates trades against dynamically scaled risk limits."""

    def __init__(self, config: Config):
        self.config = config

    def get_dynamic_limits(self, equity: float) -> dict:
        """
        Return risk limits scaled to current account equity.

        Returns dict with: max_positions, max_per_position_pct,
        stop_loss_pct, min_confidence, tier_name.
        """
        for tier in TIERS:
            if equity < tier["max_equity"]:
                limits = {
                    "tier": tier["name"],
                    "max_positions": tier["max_positions"],
                    "max_per_position_pct": tier["max_per_position_pct"],
                    "stop_loss_pct": tier["stop_loss_pct"],
                    "min_confidence": tier["min_confidence"],
                }
                log.debug(f"Tier '{tier['name']}' for equity ${equity:.2f}: {limits}")
                return limits

        # Fallback (should never reach here)
        return TIERS[-1]

    def validate_trade(
        self,
        decision: dict,
        context: dict,
    ) -> tuple[bool, str]:
        """
        Validate a trade decision against all risk rules.

        Returns:
            (approved: bool, reason: str)
        """
        equity = context["portfolio"].get("equity", 0)
        positions = context.get("positions", [])
        action = decision.get("action", "HOLD")

        # -- HOLD and SELL are always allowed ----------------
        if action == "HOLD":
            return True, "HOLD - no validation needed"

        if action == "SELL":
            # Verify we actually hold the position
            ticker = decision.get("ticker", "")
            held = [p["symbol"] for p in positions]
            if ticker and ticker not in held:
                return False, f"Cannot sell {ticker} - not in portfolio"
            return True, "SELL approved"

        # -- BUY validation ----------------------------------
        if action != "BUY":
            return False, f"Unknown action: {action}"

        limits = self.get_dynamic_limits(equity)
        ticker = decision.get("ticker", "UNKNOWN")

        # Rule 1: Minimum confidence
        confidence = float(decision.get("confidence", 0))
        if confidence < limits["min_confidence"]:
            return False, (
                f"[{ticker}] Confidence {confidence:.2f} < "
                f"minimum {limits['min_confidence']:.2f} "
                f"(tier: {limits['tier']})"
            )

        # Rule 2: Max open positions
        if len(positions) >= limits["max_positions"]:
            return False, (
                f"Max positions reached: {len(positions)}/{limits['max_positions']} "
                f"(tier: {limits['tier']})"
            )

        # AI proposed amount
        amount_raw = decision.get("amount_pct", 0)
        try:
            if isinstance(amount_raw, str):
                amount_raw = amount_raw.replace("%", "").strip()
            amount_pct = float(amount_raw)
        except ValueError:
            log.warning(f"[{ticker}] Invalid amount_pct format from AI: {amount_raw}")
            amount_pct = 0.0

        # -- Dynamic Risk Sizing based on Confidence and Sentiment --
        sentiment = context.get("prefetched_sentiment", {}).get(ticker, {})
        hype_level = sentiment.get("hype_level", "UNKNOWN")
        sentiment_score = sentiment.get("sentiment_score", 0)

        if confidence > 0.85 and hype_level == "HIGH" and sentiment_score > 0:
            log.info(f"[{ticker}] Amplifier: Extremely strong signal + Reddit Hype. Confirming full position {amount_pct}%.")
        elif confidence <= 0.75 and hype_level == "LOW":
            reduced_pct = round(amount_pct * 0.70, 1)
            log.warning(
                f"[{ticker}] Dampener: Uncertain signal ({confidence}) and no hype. "
                f"Reducing proposed position from {amount_pct}% to {reduced_pct}%."
            )
            decision["amount_pct"] = reduced_pct
            amount_pct = reduced_pct

        # -- Kelly Criterion & Volatility Position Sizing (ATR) --
        ta = context.get("prefetched_ta", {}).get(ticker, {}).get("daily", {})
        atr_pct = ta.get("ATR_pct")
        ai_stop = decision.get("stop_loss_pct")
        ai_profit = decision.get("take_profit_pct")

        if atr_pct and ai_stop:
            try:
                ai_stop_float = max(float(ai_stop), 1.0)
                
                # Kelly Calculation
                win_rate_str = context.get("state_summary", {}).get("win_rate", "0%")
                try:
                    if not win_rate_str or win_rate_str == "N/A":
                        win_rate = 0.0
                    else:
                        win_rate = float(win_rate_str.replace("%", "")) / 100.0
                except ValueError:
                    win_rate = 0.0
                
                fixed_risk_pct = 1.5 # default
                if win_rate > 0.3 and ai_profit:
                    ai_profit_float = max(float(ai_profit), 1.0)
                    risk_reward = ai_profit_float / ai_stop_float
                    if risk_reward > 0:
                        kelly = win_rate - ((1.0 - win_rate) / risk_reward)
                        half_kelly = max(0.01, kelly / 2.0) # at least 1% risk if W is low but AI wants it
                        fixed_risk_pct = round(half_kelly * 100, 2)
                        # Cap risk at 5% of portfolio per trade
                        fixed_risk_pct = min(fixed_risk_pct, 5.0)

                if ai_stop_float > 0:
                    suggested_amount_pct = round((fixed_risk_pct / ai_stop_float) * 100, 2)
                    log.info(
                        f"[{ticker}] Volatility/Kelly Sizing (ATR={atr_pct}%, SL={ai_stop_float}%, Kelly Risk={fixed_risk_pct}%): "
                        f"AI proposed {amount_pct}%, adjusting to {suggested_amount_pct}%."
                    )
                    amount_pct = suggested_amount_pct
                    decision["amount_pct"] = amount_pct
            except ValueError:
                pass

        # Rule 3: Position size limits (clipping)
        max_pct = limits["max_per_position_pct"]
        if amount_pct > max_pct:
            log.warning(
                f"[{ticker}] AI wants {amount_pct}%, but max for tier "
                f"'{limits['tier']}' is {max_pct}% - clipping order size."
            )
            amount_pct = max_pct
            decision["amount_pct"] = max_pct

        if amount_pct <= 0:
            return False, f"[{ticker}] Invalid amount_pct: {amount_pct}"

        # Rule 4: No duplicate positions
        held_symbols = [p["symbol"] for p in positions]
        if ticker.upper() in held_symbols:
            return False, f"Already holding {ticker}"

        # Rule 5: Daily loss limit (total unrealized P&L)
        total_unrealized_pct = sum(
            float(p.get("unrealized_plpc", 0)) for p in positions
        )
        if total_unrealized_pct < -(self.config.DAILY_LOSS_LIMIT_PCT / 100):
            return False, (
                f"Daily loss limit breached: "
                f"{total_unrealized_pct * 100:.1f}% "
                f"(limit: -{self.config.DAILY_LOSS_LIMIT_PCT}%)"
            )

        # Check buying power
        buying_power = context["portfolio"].get("buying_power", 0)

        # Rule 6: Minimum notional check and Buying Power limits
        notional = equity * (amount_pct / 100)

        if notional > buying_power:
            log.warning(
                f"[{ticker}] Notional ${notional:.2f} exceeds buying power ${buying_power:.2f} "
                f"- clipping order size."
            )
            notional = buying_power
            # Recalculate amount_pct for logs
            amount_pct = (notional / equity) * 100 if equity > 0 else 0
            decision["amount_pct"] = round(amount_pct, 2)

        if notional < 1.0:
            return False, (
                f"[{ticker}] Notional ${notional:.2f} < $1 minimum (BP: ${buying_power:.2f})"
            )

        # Rule 7: Validate dynamic risk-reward ratio (if AI proposed one)
        ai_stop = decision.get("stop_loss_pct")
        ai_profit = decision.get("take_profit_pct")

        if ai_stop is not None:
            ai_stop = float(ai_stop)
            # Sanity bounds: stop-loss must be between 1% and 10%
            if ai_stop < 1.0 or ai_stop > 10.0:
                log.warning(
                    f"[{ticker}] AI stop_loss_pct {ai_stop}% outside bounds "
                    f"(1-10%) - clamping to tier default {limits['stop_loss_pct']}%"
                )
                decision["stop_loss_pct"] = limits["stop_loss_pct"]

        if ai_stop is not None and ai_profit is not None:
            ai_stop = float(decision.get("stop_loss_pct", ai_stop))
            ai_profit = float(ai_profit)
            # Risk:Reward must be at least 1:2
            if ai_profit < ai_stop * 2:
                log.warning(
                    f"[{ticker}] Risk:reward {ai_stop}:{ai_profit} < 1:2 - "
                    f"adjusting take_profit to {ai_stop * 2}%"
                )
                decision["take_profit_pct"] = ai_stop * 2

        # [OK] All checks passed
        rr_info = ""
        if ai_stop is not None:
            rr_info = (
                f", SL={float(decision.get('stop_loss_pct', 0))}%, "
                f"TP={float(decision.get('take_profit_pct', 0))}%"
            )
        log.info(
            f"[OK] Trade APPROVED: BUY {ticker} {amount_pct}% "
            f"(${notional:.2f}, conf={confidence:.2f}, "
            f"tier={limits['tier']}{rr_info})"
        )
        return True, "Approved"

