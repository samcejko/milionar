"""
News search via DuckDuckGo.

Uses the duckduckgo-search library (no API key required) to find
trending financial news and topic-specific articles.
"""

import logging

from ddgs import DDGS

log = logging.getLogger("milionar.news")


class NewsSearch:
    """Search for financial news using DuckDuckGo (free, no API key)."""

    # Default queries for trending financial news
    TRENDING_QUERIES = [
        "stock market news today",
        "cryptocurrency news today",
        "best performing stocks this week",
        "trending investments 2026",
    ]

    def search_trending(self) -> list[dict]:
        """
        Get a batch of trending financial news.
        Runs multiple queries and deduplicates by title.
        """
        results = []
        seen_titles = set()

        for query in self.TRENDING_QUERIES:
            articles = self._search(query, max_results=5)
            for article in articles:
                title = article.get("title", "")
                if title and title not in seen_titles:
                    seen_titles.add(title)
                    results.append(article)

        log.info(f"Fetched {len(results)} trending news articles")
        return results

    def search_topic(self, query: str) -> list[dict]:
        """Search for news about a specific topic (called by LLM tool)."""
        results = self._search(query, max_results=5)
        log.info(f"Found {len(results)} articles for '{query}'")
        return results

    def _search(self, query: str, max_results: int = 5) -> list[dict]:
        """Execute a DuckDuckGo news search with error handling."""
        try:
            with DDGS() as ddgs:
                raw = ddgs.news(query, max_results=max_results)
                return [
                    {
                        "title": item.get("title", ""),
                        "snippet": item.get("body", "")[:300],
                        "url": item.get("url", ""),
                        "date": item.get("date", ""),
                        "source": item.get("source", ""),
                    }
                    for item in (raw or [])
                ]
        except Exception as e:
            log.warning(f"DuckDuckGo search failed for '{query}': {e}")
            return []
