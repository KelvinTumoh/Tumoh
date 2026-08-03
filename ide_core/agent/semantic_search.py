"""Embedding/text-based semantic code search with result caching."""

from __future__ import annotations

import math
from typing import Awaitable, Callable, Dict, List, Optional, Tuple


class SemanticSearch:
    """Search indexed text chunks by embedding similarity."""

    def __init__(
        self,
        embed: Optional[Callable[[str], Awaitable[List[float]]]] = None,
        cache: Optional[Dict[str, List[float]]] = None,
    ) -> None:
        self._embed = embed
        self._cache: Dict[str, List[float]] = cache if cache is not None else {}

    async def index(self, chunks: Dict[str, str]) -> None:
        """Embed and cache every chunk not already in the cache."""
        if self._embed is None:
            return
        for key, text in chunks.items():
            if key not in self._cache:
                self._cache[key] = await self._embed(text)

    def search(
        self, query_embedding: List[float], top_k: int = 5
    ) -> List[Tuple[str, float]]:
        """Return the ``top_k`` most similar cached chunks."""
        results: List[Tuple[str, float]] = []
        for key, emb in self._cache.items():
            sim = _cosine_similarity(query_embedding, emb)
            results.append((key, sim))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def search_text(
        self, query: str, top_k: int = 5
    ) -> List[Tuple[str, float]]:
        """Fallback substring search over cached chunk text."""
        results: List[Tuple[str, float]] = []
        for key, emb in self._cache.items():
            text = key.lower()
            score = 1.0 if query.lower() in text else 0.0
            results.append((key, score))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
