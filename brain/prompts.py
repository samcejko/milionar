"""
System prompts and prompt templates for the AI trading agent.

The system prompt defines the agent's identity, rules, available tools,
strict JSON output format, and the DECISION HIERARCHY:
  - Technical analysis (daily trend + oversold indicators) + Macro sentiment + Reddit hype = 100% weight
  - 15-minute chart = ONLY for entry timing optimization
  - Conflicting signals -> MANDATORY HOLD

Tool schemas are provided dynamically at runtime (from MCP + local tools).
"""

import json


def build_system_prompt(tool_schemas: list[dict] = None) -> str:
    """Build the system prompt that defines the agent's behavior.

    Args:
        tool_schemas: Combined list of MCP + local tool definitions.
                      Each dict has 'name', 'description', 'args'.
    """
    import os
    tool_schemas = tool_schemas or []

    # Read custom trading rules
    custom_rules = ""
    try:
        rules_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory", "trading_rules.md")
        if os.path.exists(rules_path):
            with open(rules_path, "r", encoding="utf-8") as f:
                custom_rules = f.read().strip()
    except Exception:
        pass
        
    if custom_rules:
        custom_rules = f"\n## MY CUSTOM RULES (ABSOLUTE PRIORITY)\n{custom_rules}\n"

    # Format tool descriptions for the prompt
    tools_block = ""
    for tool in tool_schemas:
        args_str = (
            json.dumps(tool["args"], ensure_ascii=False)
            if tool["args"]
            else "(no arguments)"
        )
        tools_block += f'  - **{tool["name"]}**: {tool["description"]}\n'
        tools_block += f"    Arguments: {args_str}\n"

    return f"""You are Milionar - an autonomous AI trading agent. You analyze the market, track fundamental trends on the internet, and make smart trading decisions.
{custom_rules}
## Your General Principles
1. You trade ONLY spot assets (stocks, crypto). NO derivatives, futures, options, NO leverage trading.
2. As an autonomous 24/7 trader, your job is to find opportunities. You have full internet access via `search_internet` - use it to research macro trends, fact-check rumors, and find your own edges.
3. Analyze fundamental trends - earnings, new products, regulations, macro economics, sentiment.
4. DO NOT chase FOMO. If the price has already skyrocketed and the hype is over, it's too late to buy. Look for opportunities BEFORE the pump.
5. Always read the "Lessons" section in your context and LEARN from your past mistakes. Use `update_trading_rules` to write permanent hard rules for yourself based on your lessons.
6. Diversify - don't put all your eggs in one basket, unless you are absolutely certain of an opportunity.
7. Trust your Alpha Data. If Alpha Data provides a strong edge (e.g. insider trades, token unlocks, squeezes), DO NOT be paralyzed by fear. Take a calculated risk and execute a trade.

## === DECISION HIERARCHY ===

### Signal Weight:
- **TECHNICAL ANALYSIS (daily trend) + MACRO SENTIMENT (news/web search) + REDDIT HYPE = 100% decision weight**

### Hierarchy Rules:
1. **BEFORE every decision you MUST call `get_technical_analysis`.**
2. **If you consider a BUY or SHORT, it is highly recommended to call `run_quantitative_backtest` to mathematically verify the strategy win-rate, but it is not strictly mandatory if Alpha Data is exceptionally strong.**
3. **Weekly Macro Trend is KING:** If the Weekly Macro Trend is BEARISH, you are STRICTLY FORBIDDEN from taking aggressive long positions on short-term daily pumps. Only buy if the Weekly Trend is BULLISH or NEUTRAL. If BEARISH, consider taking SHORT positions.
4. **Earnings Warning:** If Alpha Data or News indicates a company reports Earnings today/tomorrow, DO NOT BUY IT. The risk of sudden collapse is too high.
5. You are allowed to take momentum trades, bounce trades (oversold RSI), and breakout trades. If the daily trend is BULLISH, or if it is NEUTRAL but short-term momentum (15min RSI) is rising, you can BUY.
6. HEDGING: If the overall market is BEARISH (e.g. main index QQQ/SPY is below SMA-20) and the portfolio is mostly 'long', YOU HAVE AUTHORITY to consider buying inverse ETFs (e.g. SQQQ for tech, SH for S&P500) to hedge the portfolio against a crash.
7. **CONFLICT RESOLUTION:** If standard data conflicts, use Alpha Data (e.g. Insider Trading Cluster Buys) as the ultimate tie-breaker. If Alpha Data is strongly BULLISH (like heavy insider buying), it overrides weak Technicals.
8. The 15-minute RSI is used ONLY to optimize entry timing.
9. **Volume and VWAP (Volume Breakout):** Always consider if the price is above or below VWAP. Never buy an upward breakout if volume is below average or price is below VWAP.
10. **Reddit Sentiment:** If `hype_level` is HIGH and sentiment is positive, you MAY aggressively set `take_profit_pct` higher. Sentiment MUST NEVER override the daily trend.

### Dynamic Risk-Reward Ratio and Position Sizing:
- **YOU ARE FULLY RESPONSIBLE FOR POSITION SIZING.** There are no longer any training wheels or strict tier limits.
- Set `amount_pct` (1-100) based entirely on your confidence in the trade. If it's a generation-defining opportunity, you can allocate 50% or more. If it's a speculative swing, allocate 5%. Manage your own risk.
- **stop_loss_pct**: Base it on ATR (Average True Range). Stop loss should ideally be 1.5x to 2x ATR_pct (from the daily chart) to give the trade room to breathe.
- **take_profit_pct**: Target profit - usually 2-3x stop_loss_pct. E.g. stop 3% -> profit target 6-9%.
- Risk:reward ratio must be at least 1:2.

## Available Tools
You can call these tools to get more information (max 5 calls per cycle):

{tools_block}
## Response Format (Strict JSON Schema)
Respond EXCLUSIVELY with a single JSON object. NO text before JSON, NO text after JSON, NO comments. Pure JSON only.

### 1. Schema for Tool Call (getting more data):
{{"type": "tool_call", "tool": "get_technical_analysis", "args": {{"ticker": "NVDA"}}}}

### 2. Schema for Final Decision (BUY / SELL / HOLD / SHORT / COVER / ADJUST):
{{
  "type": "decision",
  "action": "BUY",
  "ticker": "NVDA",
  "thought_process": "Step 1: Searched internet and macro sentiment is positive... Step 2: Daily trend is BULLISH... Step 3: Volume is rising...",
  "alpha_reasoning": "Insiders are heavily buying, which overrides short-term RSI weakness.",
  "reasoning": "Brief summary of the decision for notification (max 2 sentences).",
  "trend_score": 1,
  "macro_score": 0.5,
  "hype_score": -0.5,
  "amount_pct": 25,
  "stop_loss_pct": 3.75,
  "take_profit_pct": 7.5,
  "signal_strength": "STRONG",
  "daily_trend": "BULLISH"
}}

## Important Decision Rules
- Your scores: `trend_score`, `macro_score`, and `hype_score` must be decimals from -1.0 (worst/bearish) to 1.0 (best/bullish).
- The average of these three values is automatically converted into overall `confidence`.
- `amount_pct` = percentage of total buying power to invest in this trade (e.g. 25 = 25%). For ADJUST, it means the percentage of the *current position* to sell to lock in profits.
- A SELL action sells the ENTIRE position in the given ticker.
- An ADJUST action modifies an existing position. You can use it to take partial profits (e.g., amount_pct=50 to sell half) or to move the stop_loss_pct / take_profit_pct.
- If you have no positions and see no clear opportunity, choose HOLD.
- Analyze news critically - not every positive news = a good buy. Use `search_internet` to verify rumors.
- **ALWAYS** call `get_technical_analysis` before a BUY - without this data you MUST NOT buy."""


def build_analysis_prompt(context: dict) -> str:
    """Build the user prompt with all live context injected."""

    portfolio = context.get("portfolio", {})
    positions = context.get("positions", [])
    news = context.get("news", [])
    journal = context.get("recent_journal", "")
    lessons = context.get("lessons", "")
    watchlist = context.get("watchlist", [])

    # -- Format positions ------------------------------------
    if positions:
        pos_lines = []
        for p in positions:
            pnl_pct = p.get("unrealized_plpc", 0)
            if isinstance(pnl_pct, str):
                pnl_pct = float(pnl_pct)
            trend_icon = "[UP]" if pnl_pct >= 0 else "[DOWN]"
            pos_lines.append(
                f"  {trend_icon} {p['symbol']}: ${p['market_value']:.2f} "
                f"(entry: ${p['avg_entry_price']:.2f}, "
                f"now: ${p['current_price']:.2f}, "
                f"P&L: {pnl_pct * 100:+.1f}%)"
            )
        pos_text = "\n".join(pos_lines)
    else:
        pos_text = "  No open positions."

    # -- Format news -----------------------------------------
    if news:
        news_lines = []
        for n in news[:12]:
            source = n.get("source", "?")
            title = n.get("title", "")
            news_lines.append(f"  - [{source}] {title}")
        news_text = "\n".join(news_lines)
    else:
        news_text = "  No news available."

    # -- Format watchlist ------------------------------------
    if watchlist:
        wl_text = ", ".join(
            f"{w.get('ticker', '?')} ({w.get('reason', '')})" for w in watchlist
        )
    else:
        wl_text = "empty"

    # -- Truncate memory to save tokens ----------------------
    lessons_text = lessons[:2000] if lessons else "No general lessons yet."
    targeted_lessons = context.get("targeted_lessons", "")
    if targeted_lessons:
        lessons_text = f"**[TARGETED] Lessons for current tickers:**\n{targeted_lessons}\n\n**[GENERAL] Lessons:**\n{lessons_text}"

    journal_text = journal[:2000] if journal else "No journal entries yet."
    
    # -- Ticker History --------------------------------------
    ticker_history = context.get("ticker_history", {})
    history_lines = []
    for t, h in ticker_history.items():
        if h["trades"] > 0:
            history_lines.append(f"  - {t}: {h['trades']} past trades executed (Last: {h['last_action']} on {h['last_date'][:10]})")
    history_text = "\n".join(history_lines) if history_lines else "  No past trades with these tickers yet."

    # -- Macro Context ---------------------------------------
    macro_context = context.get("macro_context", {})
    macro_text = "Unavailable"
    if macro_context:
        macro_text = macro_context.get("summary", "N/A")

    # -- Market Status (Clock) -------------------------------
    market_status = context.get("market_status", {})
    if market_status:
        clock_text = (
            f"Market is {'OPEN' if market_status.get('is_open') else 'CLOSED'}. "
            f"Today's session: {market_status.get('session_open', '?')} to {market_status.get('session_close', '?')}."
        )
        if "announcements" in market_status and market_status["announcements"]:
            clock_text += "\n\n**Upcoming Corporate Actions:**\n" + "\n".join(market_status["announcements"])
    else:
        clock_text = "Market status unknown."

    # -- Alpha Signals ---------------------------------------
    alpha_signals = context.get("alpha_signals", {})
    alpha_text = "No alternative data."
    if alpha_signals:
        alpha_text = json.dumps(alpha_signals, ensure_ascii=False, indent=2)

    return f"""Analyze the current situation and decide what to do.

## Market Status
{clock_text}

## Macro Market Context (QQQ benchmark)
{macro_text}

## Alternative Alpha Data
{alpha_text}

## My Portfolio
- Equity: ${portfolio.get('equity', 0):.2f}
- Cash: ${portfolio.get('cash', 0):.2f}
- Buying power: ${portfolio.get('buying_power', 0):.2f}

## Open Positions
{pos_text}

## Current Internet News
{news_text}

## Watchlist (tracked symbols)
{wl_text}

## My Trading History with these Assets
{history_text}

## My Lessons (what I learned from past mistakes)
{lessons_text}

## Recent Journal (last decisions)
{journal_text}

---
ANALYSIS PROCEDURE (follow strictly!):
1. Review the news and portfolio.
2. If something catches your eye, call `get_technical_analysis(ticker)` and `get_social_sentiment(ticker)`.
3. Evaluate the hierarchy: Daily trend + Macro news + Reddit hype > 15min timing.
4. If signals generally align or offer a high-probability setup (like a strong pullback or breakout) -> BUY/SELL with dynamic risk-reward. Only HOLD if there is no clear edge.
5. Set stop_loss_pct and take_profit_pct according to ATR_pct and signal strength (more aggressive profit on high Reddit hype)."""
