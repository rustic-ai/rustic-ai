from typing import List

from ..kbindex_backend import SearchResult
from ..plugins import RerankerPlugin
from ..query import SearchQuery


class NoOpReranker(RerankerPlugin):
    """A reranker that does nothing and returns the results as is."""

    async def rerank(
        self,
        *,
        results: List[SearchResult],
        query: SearchQuery,
    ) -> List[SearchResult]:
        return results
