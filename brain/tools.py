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
from brain.backtest import run_quantitative_backtest

log = logging.getLogger("milionar.tools")


# ── Local tool schemas (tools NOT available via MCP) ─────────

LOCAL_TOOL_DESCRIPTIONS = [
    {
        "name": "search_news",
        "description": "Vyhledá zprávy na internetu k zadanému tématu (DuckDuckGo)",
        "args": {"query": "string — hledaný výraz, např. 'NVIDIA earnings 2026'"},
    },
    {
        "name": "search_internet",
        "description": (
            "Prohledá celý internet pomocí vyhledávače DuckDuckGo. "
            "Použij k nalezení jakýchkoliv informací, faktů, nebo trendů, které potřebuješ "
            "k utvoření makroekonomického obrazu nebo vyhledání konkrétní zprávy."
        ),
        "args": {"query": "string — hledaný výraz, např. 'US Federal Reserve interest rates today'"},
    },
    {
        "name": "search_wikipedia",
        "description": (
            "Získá kompletní a detailní shrnutí (summary) z Wikipedie pro dané téma. "
            "Zavolej tuto funkci, pokud narazíš na neznámou firmu, technologii nebo makroekonomický koncept a potřebuješ detailní porozumění."
        ),
        "args": {"query": "string — hledaný výraz v angličtině (přesný název článku, např. 'Nvidia', 'Quantum computing')"},
    },
    {
        "name": "search_twitter",
        "description": (
            "Prohledá sociální síť Twitter (X) pro daný klíčový výraz. "
            "Tento nástroj je perfektní pro lovení aktuálního sentimentu lidí ohledně kryptoměn nebo meme akcií."
        ),
        "args": {"query": "string — hledaný výraz, např. 'Bitcoin ETF' nebo 'Tesla FSD'"},
    },
    {
        "name": "update_trading_rules",
        "description": (
            "Slouží k uložení nebo odstranění tvých vlastních obchodních pravidel. "
            "Pokud z historie nebo analýzy zjistíš něco důležitého (např. 'Nikdy nekupovat akcie z Číny' "
            "nebo 'Při velkém VIXu snížit pozice'), použij tento nástroj. Tato pravidla se ti vždy "
            "načtou na začátku tvých instrukcí."
        ),
        "args": {"action": "string — 'ADD' nebo 'REMOVE'", "rule": "string — samotné pravidlo"},
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
        "name": "run_quantitative_backtest",
        "description": (
            "Provede rychlý matematický backtest za posledních 180 dní pro daný ticker. "
            "Simuluje nákupy a prodeje podle Mean Reversion strategie a vrátí Win Rate (šanci na výhru). "
            "Silně doporučeno zavolat před nákupem, abys matematicky ověřil, zda se akcii vyplatí obchodovat."
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
    {
        "name": "read_youtube_video",
        "description": (
            "Stáhne a přečte kompletní textový přepis (transcript) z YouTube videa. "
            "Zavolej tuto funkci kdykoliv narazíš na odkaz na YouTube a potřebuješ zjistit, "
            "co se ve videu přesně říká, místo hádání z clickbaitového názvu."
        ),
        "args": {"url": "string — kompletní URL adresa YouTube videa"},
    },
]


class ToolRegistry:
    """
    Hybrid tool registry: MCP + local tools.

    MCP tools are forwarded to the Alpaca MCP server via McpToolProvider.
    Local tools (search_news, get_technical_analysis, get_social_sentiment, run_quantitative_backtest)
    are executed directly in-process.
    """

    def __init__(self, mcp_provider, news_search, config: Config):
        self.mcp = mcp_provider
        self.news = news_search
        self.config = config

        # Local tool dispatch table
        self._local_tools = {
            "search_news": self._search_news,
            "search_internet": self._search_internet,
            "search_wikipedia": self._search_wikipedia,
            "search_twitter": self._search_twitter,
            "update_trading_rules": self._update_trading_rules,
            "get_technical_analysis": self._get_technical_analysis,
            "get_social_sentiment": self._get_social_sentiment,
            "run_quantitative_backtest": self._run_quantitative_backtest,
            "read_youtube_video": self._read_youtube_video,
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

    def _search_internet(self, query: str) -> list:
        from ddgs import DDGS
        try:
            with DDGS() as ddgs:
                results = ddgs.text(query, max_results=5)
                return [{"title": r.get("title", ""), "body": r.get("body", ""), "href": r.get("href", "")} for r in results]
        except Exception as e:
            return [{"error": str(e)}]

    def _search_wikipedia(self, query: str) -> dict:
        import urllib.request
        import urllib.parse
        try:
            # Using Wikipedia REST API to get summary
            safe_query = urllib.parse.quote(query)
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{safe_query}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode())
                    return {"title": data.get("title"), "summary": data.get("extract")}
        except Exception as e:
            return {"error": f"Wikipedia search failed: {e}"}
        return {"error": "Not found"}

    def _search_twitter(self, query: str) -> list:
        from ddgs import DDGS
        try:
            twitter_query = f"{query} (site:twitter.com OR site:x.com)"
            with DDGS() as ddgs:
                results = ddgs.text(twitter_query, max_results=5)
                return [{"tweet": r.get("body", ""), "link": r.get("href", "")} for r in results]
        except Exception as e:
            return [{"error": str(e)}]

    def _update_trading_rules(self, action: str, rule: str) -> dict:
        import os
        from datetime import datetime
        filepath = os.path.join(self.config.MEMORY_DIR, "trading_rules.md")
        
        # Ensure file exists
        if not os.path.exists(filepath):
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("# Vlastní Pravidla Tradingu\n\n")

        with open(filepath, "a", encoding="utf-8") as f:
            if action.upper() == "ADD":
                f.write(f"- [ADDED {datetime.now().strftime('%Y-%m-%d %H:%M')}] {rule}\n")
            elif action.upper() == "REMOVE":
                f.write(f"- [REMOVED {datetime.now().strftime('%Y-%m-%d %H:%M')}] {rule}\n")
        
        log.info(f"Updated trading rules: {action} {rule}")
        return {"status": "success", "message": f"Rule '{rule}' logged as {action}."}

    async def _get_technical_analysis(self, ticker: str) -> dict:
        return await get_technical_analysis(ticker, self.config)


    async def _get_social_sentiment(self, ticker: str) -> dict:
        return await get_social_sentiment(ticker)

    async def _run_quantitative_backtest(self, ticker: str) -> dict:
        from market.data import MarketData
        md = MarketData(self.config)
        try:
            return await run_quantitative_backtest(ticker, md)
        finally:
            await md.close()

    def _read_youtube_video(self, url: str) -> dict:
        import urllib.parse as urlparse
        from youtube_transcript_api import YouTubeTranscriptApi
        
        try:
            parsed = urlparse.urlparse(url)
            video_id = ""
            if "youtube.com" in parsed.netloc:
                qs = urlparse.parse_qs(parsed.query)
                video_id = qs.get("v", [""])[0]
            elif "youtu.be" in parsed.netloc:
                video_id = parsed.path.lstrip("/")
                
            if not video_id:
                return {"error": "Invalid YouTube URL format."}
                
            # Fetch transcript (tries Czech first, then English, then any available)
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            try:
                transcript = transcript_list.find_transcript(['cs', 'en'])
            except:
                # Fallback to the first available if cs/en not found
                transcript = next(iter(transcript_list))
                
            data = transcript.fetch()
            
            # Combine all text blocks
            full_text = " ".join([t['text'] for t in data])
            
            return {
                "success": True,
                "video_id": video_id,
                "language": transcript.language,
                "transcript": full_text
            }
        except Exception as e:
            return {"error": f"Failed to extract transcript: {str(e)}"}
