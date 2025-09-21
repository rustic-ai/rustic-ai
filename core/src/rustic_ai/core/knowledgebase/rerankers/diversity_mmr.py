from collections import Counter, defaultdict
import math
from typing import Dict, List

from pydantic import Field

from ..kbindex_backend import SearchResult
from ..plugins import RerankerPlugin
from ..query import SearchQuery


class MMRDiversityReranker(RerankerPlugin):
    """Maximal Marginal Relevance using TF-IDF cosine as similarity.

    Promotes diversity while maintaining relevance.
    """

    lambda_: float = Field(default=0.7, ge=0.0, le=1.0)
    top_k: int = Field(default=10)

    def _tokenize(self, text: str) -> List[str]:
        return [t for t in (text or "").lower().split() if t]

    def _get_text_from_result(self, result: SearchResult) -> str:
        text = ""
        payload = result.payload
        if isinstance(payload, dict):
            if "chunk" in payload and isinstance(payload["chunk"], dict) and "text" in payload["chunk"]:
                text = payload["chunk"]["text"]
            elif "text" in payload:
                text = payload.get("text", "")
            elif "content" in payload:
                text = payload.get("content", "")
        return text

    def _tfidf_vectors(self, results: List[SearchResult]):
        texts = [self._get_text_from_result(r) for r in results]
        toks_list = [self._tokenize(t) for t in texts]
        df: Dict[str, int] = defaultdict(int)
        for toks in toks_list:
            for t in set(toks):
                df[t] += 1
        N = max(1, len(toks_list))
        idf = {t: math.log((N + 1) / (c + 1)) + 1.0 for t, c in df.items()}

        vecs: List[Dict[str, float]] = []
        norms: List[float] = []
        for toks in toks_list:
            tf = Counter(toks)
            w = {t: tf[t] * idf.get(t, 0.0) for t in tf}
            vecs.append(w)
            norms.append(math.sqrt(sum(v * v for v in w.values())) or 1.0)
        return vecs, norms

    def _cosine(self, a: dict, b: dict, na: float, nb: float) -> float:
        keys = set(a) | set(b)
        dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in keys)
        return dot / (na * nb) if na * nb > 0 else 0.0

    async def rerank(
        self,
        *,
        results: List[SearchResult],
        query: SearchQuery,
    ) -> List[SearchResult]:
        if not results:
            return results
        vecs, norms = self._tfidf_vectors(results)

        selected_indices: List[int] = []
        remaining_indices = list(range(len(results)))

        # Use initial score as the relevance score
        relevance_scores = [r.score for r in results]

        k = min(self.top_k, len(results))
        while remaining_indices and len(selected_indices) < k:
            best_idx = -1
            best_val = -1e9
            for i in remaining_indices:
                max_sim = 0.0
                if selected_indices:
                    # Calculate max similarity with already selected documents
                    max_sim = max(self._cosine(vecs[i], vecs[j], norms[i], norms[j]) for j in selected_indices)

                val = self.lambda_ * relevance_scores[i] - (1 - self.lambda_) * max_sim
                if val > best_val:
                    best_val = val
                    best_idx = i

            if best_idx != -1:
                selected_indices.append(best_idx)
                remaining_indices.remove(best_idx)

        # Build the final list of results in the new order
        reranked_results = [results[i] for i in selected_indices]

        # Add the remaining documents that were not selected
        for i in range(len(results)):
            if i not in selected_indices:
                reranked_results.append(results[i])

        # Update scores to reflect the new ranking (optional, but good practice)
        for i, res in enumerate(reranked_results):
            res.score = float(len(reranked_results) - i)

        return reranked_results
