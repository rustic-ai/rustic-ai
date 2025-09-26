from collections import Counter, defaultdict
import math
from typing import Dict, List

from pydantic import Field

from ..kbindex_backend import SearchResult
from ..plugins import RerankerPlugin
from ..query import SearchQuery


class BM25LiteReranker(RerankerPlugin):
    """Simple BM25 scoring over candidate set.

    Uses approximate DF from candidates; good enough for post-retrieval rerank.
    """

    k1: float = Field(default=1.2)
    b: float = Field(default=0.75)

    def _tokenize(self, text: str) -> List[str]:
        return [t for t in (text or "").lower().split() if t]

    async def rerank(
        self,
        *,
        results: List[SearchResult],
        query: SearchQuery,
    ) -> List[SearchResult]:
        qtext = query.text or ""
        if not results or not qtext:
            return results

        # This reranker operates on text; we need to extract it from payloads
        # We assume the payload contains the original TextChunk model or a dict
        # with a 'text' field.
        docs: List[List[str]] = []
        doc_lengths: List[int] = []
        df: Dict[str, int] = defaultdict(int)

        for res in results:
            text = ""
            payload = res.payload
            if isinstance(payload, dict):
                # Heuristic: check for a TextChunk-like structure or a simple 'text' field
                if "chunk" in payload and isinstance(payload["chunk"], dict) and "text" in payload["chunk"]:
                    text = payload["chunk"]["text"]
                elif "text" in payload:
                    text = payload.get("text", "")
                elif "content" in payload:  # Fallback for older format
                    text = payload.get("content", "")

            toks = self._tokenize(text)
            docs.append(toks)
            doc_lengths.append(len(toks))
            for t in set(toks):
                df[t] += 1

        avgdl = (sum(doc_lengths) / len(doc_lengths)) if doc_lengths else 1.0
        N = max(1, len(docs))
        idf = {t: math.log(1 + (N - c + 0.5) / (c + 0.5)) for t, c in df.items()}

        q_terms = self._tokenize(qtext)
        for i, (toks, dl) in enumerate(zip(docs, doc_lengths)):
            tf = Counter(toks)
            s = 0.0
            for t in q_terms:
                if t not in tf:
                    continue
                denom = tf[t] + self.k1 * (1 - self.b + self.b * dl / (avgdl or 1.0))
                s += idf.get(t, 0.0) * (tf[t] * (self.k1 + 1)) / (denom or 1.0)
            results[i].score = s

        return sorted(results, key=lambda r: r.score, reverse=True)
