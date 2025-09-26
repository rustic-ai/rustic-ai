from typing import List

from pydantic import Field

from ..plugins import RerankerPlugin
from ..query import SearchQuery, SearchResult


class RRFReranker(RerankerPlugin):
    """
    Applies Reciprocal Rank Fusion to a list of results.

    This implementation is a simple post-processing step that re-scores based
    on the initial rank of the items, assuming they are pre-sorted by relevance.
    It does not use a cross-encoder or LLM.
    """

    k: int = Field(60, description="RRF ranking constant.")

    async def rerank(
        self,
        *,
        results: List[SearchResult],
        query: SearchQuery,
    ) -> List[SearchResult]:
        if not results:
            return []

        # The RRF formula is applied to ranks. The initial `results` list is
        # assumed to be sorted by relevance from the retrieval stage.
        for i, result in enumerate(results):
            rank = i + 1
            result.score = 1.0 / (self.k + rank)

        # The list is now sorted by the new RRF score.
        return sorted(results, key=lambda r: r.score, reverse=True)
