"""
Hybrid tool registry — MCP tools + local tools.

MCP tools come dynamically from the Alpaca MCP Server (read-only:
account, stock-data, crypto-data). Local tools are registered here:
  - search_news: DuckDuckGo news search
  - get_technical_analysis: Multi-timeframe TA (Daily + 15min)

SECURITY: MCP never has trading toolsets enabled. All trade execution
goes through executor.py via the ACT phase.
"""

import asyncio
import json
import logging

from config import Config
from brain.technical import get_technical_analysis
from brain.sentiment import get_social_sentiment

log = logging.getLogger("milionar.tools")


# ── Local tool schemas (tools NOT available via MCP) ─────────

LOCAL_TOOL_DESCRIPTIONS = [
    {
        "name": "search_news",
        "description": "Vyhledá zprávy na internetu k zadanému tématu (DuckDuckGo)",
        "args": {"query": "string — hledaný výraz, např. 'NVIDIA earnings 2026'"},
    },
    {
        "name": "get_technical_analysis",
        "description": (
            "Multi-timeframe technická analýza pro daný ticker. "
            "Vrátí DVĚ úrovně: Denní (Daily) trend se SMA-20 a RSI-14, "
            "a krátkodobý 15minutový RSI-14 pro načasování vstupu. "
            "POVINNÉ použít PŘED nákupem — ověříš long-term trend i short-term timing."
        ),
        "args": {"ticker": "string — symbol, např. 'AAPL' nebo 'BTC/USD'"},
    },
    {
        "name": "get_social_sentiment",
        "description": (
            "Analyzuje aktuální náladu na finančním Redditu pro daný ticker. "
            "Vrací hype level a skóre (odměřuje FOMO a paniku). "
            "Sentiment představuje 20% váhy v rozhodování — při vysokém hype "
            "lze agresivněji nastavit profit_target, ale sentiment nenahrazuje trend."
        ),
        "args": {"ticker": "string — symbol, např. 'NVDA' nebo 'BTC'"},
    },
]


class ToolRegistry:
    """
    Hybrid tool registry: MCP + local tools.

    MCP tools are forwarded to the Alpaca MCP server via McpToolProvider.
    Local tools (search_news, get_technical_analysis, get_social_sentiment)
    are executed directly in-process.
    """

    def __init__(self, mcp_provider, news_search, config: Config):
        self.mcp = mcp_provider
        self.news = news_search
        self.config = config

        # Local tool dispatch table
        self._local_tools = {
            "search_news": self._search_news,
            "get_technical_analysis": self._get_technical_analysis,
            "get_social_sentiment": self._get_social_sentiment,
        }

    def get_all_tool_schemas(self) -> list[dict]:
        """
        Combine MCP tool schemas + local tool schemas.
        This is injected into the LLM system prompt.
        """
        return self.mcp.tool_schemas + LOCAL_TOOL_DESCRIPTIONS

    def is_local_tool(self, tool_name: str) -> bool:
        """Check if a tool is handled locally (not via MCP)."""
        return tool_name in self._local_tools

    async def execute(self, tool_name: str, args: dict) -> str:
        """
        Execute a tool — routes to local handler or MCP.
        Returns result as JSON string.

        This method is async because MCP calls are async.
        Local tools are sync but wrapped transparently.
        """
        # Local tools: execute directly (sync or async)
        if tool_name in self._local_tools:
            try:
                log.info(f"Executing local tool: {tool_name}({args})")
                handler = self._local_tools[tool_name]
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(**args)
                else:
                    result = await asyncio.to_thread(handler, **args)
                return json.dumps(result, ensure_ascii=False, default=str)
            except Exception as e:
                log.error(f"Local tool '{tool_name}' failed: {e}")
                return json.dumps({"error": str(e)})

        # MCP tools: forward to MCP server (async)
        return await self.mcp.call_tool(tool_name, args)

    # ── Local tool implementations ──────────────────────────

    def _search_news(self, query: str) -> list:
        return self.news.search_topic(query)

    async def _get_technical_analysis(self, ticker: str) -> dict:
        return await get_technical_analysis(ticker, self.config)


    async def _get_social_sentiment(self, ticker: str) -> dict:
        return await get_social_sentiment(ticker)
