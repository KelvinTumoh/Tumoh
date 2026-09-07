"""Simple web search client using DuckDuckGo via the ``ddgs`` package."""

from __future__ import annotations

import logging

try:
    from ddgs import DDGS
except ImportError:  # pragma: no cover
    DDGS = None  # type: ignore

logger = logging.getLogger(__name__)


class WebSearchClient:
    """Lightweight wrapper around DuckDuckGo search."""

    def __init__(self, max_results: int = 3) -> None:
        self.max_results = max_results

    def search(self, query: str) -> str:
        """Return a formatted string of search snippets for ``query``.

        If the ``ddgs`` package is not installed or the search fails, an
        empty string is returned so the LLM can fall back to its own
        knowledge.
        """
        if DDGS is None:
            logger.warning("ddgs not installed; web search unavailable")
            return ""

        try:
            logger.info(f"🔍 Web searching: {query}")
            ddgs = DDGS()
            results = list(ddgs.text(query, max_results=self.max_results))
        except Exception:
            logger.exception("Web search failed")
            return ""

        if not results:
            return ""

        snippets: list[str] = []
        for result in results:
            title = result.get("title", "").strip()
            body = result.get("body", "").strip()
            href = result.get("href", "").strip()
            if not body:
                continue
            snippet = f"[{title}]\n{body}\nSource: {href}".strip()
            snippets.append(snippet)

        return "\n\n".join(snippets)

    @staticmethod
    def is_current_event_query(text: str) -> bool:
        """Heuristic to decide whether a question benefits from web search."""
        if not text:
            return False

        triggers = {
            "?",
            "news",
            "latest",
            "recent",
            "today",
            "current",
            "update",
            "live",
            "now",
            "status",
            "war",
            "iran",
            "usa",
            "us",
            "israel",
            "gaza",
            "ukraine",
            "russia",
            "china",
            "trump",
            "biden",
            "election",
            "stock",
            "price",
            "weather",
            "score",
            "market",
        }

        lower = text.lower()
        return "?" in text or any(trigger in lower for trigger in triggers)
