# Milionář Bot - Autonomous Algorithmic Trading System

Milionář Bot is an autonomous, AI-driven quantitative trading system designed for continuous market analysis and execution. The system operates in a continuous event-driven loop, synthesizing macroeconomic data, technical indicators, and alternative data sources (Alpha signals) to execute trades autonomously via the Alpaca API. The system incorporates dynamic risk management, machine learning parameter optimization, and high-frequency event processing.

---

## Core Architecture & Features

- **O.T.A.R. Execution Cycle (Observe -> Think -> Act -> Reflect)**: The system evaluates the market every 15 minutes, formulates hypotheses via LLM integration, executes trades, and conducts automated weekend reflection and performance analysis.
- **Event-Driven Execution (HFT)**: To optimize API utilization, the bot remains in a dormant state between standard cycles. However, it operates an interrupt-driven mechanism: if an urgent market event is detected by background processes, the execution cycle is triggered within milliseconds to process time-sensitive opportunities.
- **Speculative Mode (Risk-Adjusted Execution)**: A specialized risk tolerance protocol. If the confidence score of a generated trade signal is sub-optimal (e.g., 40-64%), the system does not discard the signal entirely. Instead, it executes a highly risk-adjusted position (capped at 0.2% of total capital) to capture potential upside with minimal downside exposure.
- **Machine Learning Parameter Optimization (Grid Search)**: An automated daily process that backtests 180 days of historical data for tracked assets. It iterates through multiple combinations of technical indicators (SMA, RSI) to identify the optimal parameters that maximize historical win rates, storing these findings for real-time application.
- **Dynamic Risk Management (Trailing Stop-Loss)**: Automated position management utilizing High-Water Marks to implement trailing stops, ensuring capital preservation and profit locking during uptrends.
- **Real-Time Telemetry**: Integrated Telegram alerts for immediate notification of executed trades and system status.

---

## Data Acquisition & Alpha Generation

The system aggregates alternative data via independent, asynchronous Python processes (Workers) running in the background. These processes are categorized by latency and data source:

### High-Frequency Trading (HFT) Monitors
Operating continuously with micro-intervals to trigger the Event-Driven execution loop.
- **`worker_hack_alerts.py` (30s interval)**: Monitors major cryptocurrency RSS feeds for security breaches and smart contract exploits, generating immediate short signals to front-run market reaction.
- **`worker_crypto_whales.py` (60s interval)**: Tracks significant blockchain movements, including institutional capital deployment (e.g., large-scale USDT minting) or exchange inflows that precede major price volatility.
- **`worker_geopolitics.py` (5m interval)**: Parses global news wires (Reuters, BBC) for geopolitical escalation keywords, prompting defensive asset rotation.

### Alternative Data Monitors
Utilizing public data endpoints to gauge market sentiment and retail behavior.
- **`worker_wsb_sentiment.py`**: Analyzes JSON data from specific financial forums (e.g., r/wallstreetbets) to measure retail momentum and volume anomalies.
- **`worker_app_store_fomo.py`**: Monitors top US App Store rankings via RSS. The sudden rise of retail trading applications serves as a contrarian indicator for market tops.
- **`worker_github_activity.py`**: Interrogates public GitHub APIs for commit frequency on major open-source blockchain repositories, identifying development spikes indicative of upcoming network upgrades.
- **`worker_wikipedia_fear.py`**: Utilizes the Wikimedia Pageviews API to track search volume for macroeconomic stress keywords (e.g., "Recession", "Bankruptcy") as a leading indicator of market panic.
- **`worker_weather_commodities.py`**: Aggregates satellite weather data via Open-Meteo to detect extreme climate conditions in key agricultural regions, facilitating predictive trades on commodity ETFs.

### Institutional & Macro Tracking
- **`worker_insider_trading.py`**: Tracks corporate executive transactions (SEC Form 4 filings).
- **`worker_pelosi_tracker.py`**: Monitors congressional stock trading disclosures.
- **`worker_value_titans.py`**: Analyzes 13F filings from prominent institutional investors (e.g., Warren Buffett, Howard Marks).
- **`worker_macro_gurus.py`**: Monitors bearish macroeconomic outlooks.
- **`worker_inverse_cathie.py`**: Generates signals based on shorting specific high-growth innovation ETFs.
- **`worker_youtube_crypto.py`**: Analyzes video transcripts from key domestic financial analysts using automated sentiment extraction.

---

## Directory Structure

### `main.py`
The central orchestrator. Initializes the terminal dashboard, launches asynchronous background processes, and manages the Event-Driven execution cycle.

### `brain/` (Logic & AI Integration)
- `thinker.py` - Interfaces with the OpenRouter LLM API. Evaluates trade viability and enforces risk management logic.
- `prompts.py` - System instructions and JSON schema definitions for the LLM.
- `backtest.py` - Quantitative backtesting module invoked by the LLM to verify mathematical probability before trade execution.
- `technical.py` - Multi-timeframe technical analysis utilizing dynamic parameters sourced from the ML Optimizer.
- `mcp_client.py` - Interface for the Alpaca Model Context Protocol (MCP) server.

### `trader/` (Execution & Risk)
- `executor.py` - Handles order routing to the Alpaca API, manages slippage, and updates trailing stops.
- `risk.py` - Dynamically adjusts position sizing based on portfolio exposure and LLM confidence scores.
- `state.py` - Persistent storage for tracking peak asset prices (High-Water Marks).

### `alpha_workers/` (Data Mining)
Directory containing all asynchronous Python scripts responsible for signal generation.

---

## Installation & Deployment

### 1. Prerequisites
- **Python 3.10+** (Compatible with standard Linux environments and Raspberry Pi hardware).
- Active accounts for [Alpaca](https://alpaca.markets) (Paper Trading mode recommended for testing), [OpenRouter](https://openrouter.ai), and [Telegram](https://telegram.org/).

### 2. Environment Configuration (`.env`)
Create a `.env` file in the root directory:
```env
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret
ALPACA_API_URL=https://paper-api.alpaca.markets
ALPACA_DATA_URL=https://data.alpaca.markets
OPENROUTER_API_KEY=your_openrouter_key
TELEGRAM_BOT_TOKEN=your_telegram_token
TELEGRAM_CHAT_ID=your_chat_id
ENABLE_YOLO_MODE=true
```

### 3. Execution
The system includes automated initialization scripts that manage virtual environments and dependencies. Graceful shutdown (including all background workers) is achieved via `Ctrl+C`.

**Linux / macOS (Raspberry Pi):**
```bash
chmod +x start.sh
./start.sh
```

**Windows:**
```powershell
.\start.ps1
```
