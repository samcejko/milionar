"""
Milionar - Central Configuration
All bot settings in one place. Risk parameters are base values;
trader/risk.py scales them dynamically based on account equity.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Immutable configuration loaded from environment + defaults."""

    # -- Paths ---------------------------------------------------
    BASE_DIR = Path(__file__).parent
    MEMORY_DIR = BASE_DIR / "memory"
    JOURNAL_DIR = MEMORY_DIR / "journal"
    LESSONS_FILE = MEMORY_DIR / "lessons.md"
    WATCHLIST_FILE = MEMORY_DIR / "watchlist.json"
    TRADES_FILE = MEMORY_DIR / "trades.jsonl"
    STATE_FILE = MEMORY_DIR / "state.json"
    LOG_DIR = BASE_DIR / "logs"
    LOG_FILE = LOG_DIR / "milionar.log"

    # -- OpenRouter (free LLM inference) -------------------------
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_URL: str = "https://openrouter.ai/api/v1/chat/completions"

    # Model fallback priority list (best -> last resort)
    MODELS: list[str] = [
        "nex-agi/nex-n2-pro:free",
        "openrouter/owl-alpha",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
    ]

    # -- Alpaca Paper Trading ------------------------------------
    ALPACA_API_KEY: str = os.getenv("ALPACA_API_KEY", "")
    ALPACA_SECRET_KEY: str = os.getenv("ALPACA_SECRET_KEY", "")
    ALPACA_BASE_URL: str = os.getenv(
        "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"
    )
    ALPACA_DATA_URL: str = "https://data.alpaca.markets"

    # -- MCP (Alpaca tool server) --------------------------------
    # Only read-only toolsets! Trading goes through executor.py/risk.py.
    MCP_TOOLSETS: str = os.getenv(
        "MCP_TOOLSETS", "account,stock-data,crypto-data,assets,corporate-actions,news,fixed-income-data,index-data"
    )

    # -- Telegram Notifications (optional) -----------------------
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # -- Main Loop -----------------------------------------------
    CYCLE_INTERVAL_MINUTES: int = 15
    MAX_TOOL_CALLS: int = 30

    # -- Risk Management Base Limits (Dynamically scaled) --------
    MAX_POSITIONS: int = 10
    MAX_POSITION_PCT: float = 0.15
    MIN_CONFIDENCE: float = 0.7
    ENABLE_YOLO_MODE: bool = True  # Toggle for extreme asymmetric risk bets
    MAX_DAILY_TRADES: int = 5            # Hard kill-switch: max trades per day

    # -- Risk Management (base values - risk.py overrides dynamically)
    STOP_LOSS_PCT: float = 5.0          # Per-position stop-loss
    DAILY_LOSS_LIMIT_PCT: float = 3.0   # Max daily drawdown
    TOTAL_LOSS_LIMIT_PCT: float = 10.0  # Emergency shutdown threshold
    TRAILING_STOP_PERCENT: float = 5.0  # Trailing stop: sell if price drops this % from high

    @classmethod
    def ensure_dirs(cls) -> None:
        """Create necessary directories if they don't exist."""
        cls.MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        cls.JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOG_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def validate(cls) -> list[str]:
        """Check that required API keys are set. Returns list of errors."""
        errors = []
        if not cls.OPENROUTER_API_KEY:
            errors.append("OPENROUTER_API_KEY is not set in .env")
        if not cls.ALPACA_API_KEY:
            errors.append("ALPACA_API_KEY is not set in .env")
        if not cls.ALPACA_SECRET_KEY:
            errors.append("ALPACA_SECRET_KEY is not set in .env")
        return errors
