from __future__ import annotations

import time
from typing import Dict, List, Tuple
import uuid

from .config import KBConfig
from .kbindex_backend import KBIndexBackend
from .query import (
    ExplainData,
    ExplainTargetStat,
    FusionStrategy,
    NormalizationMethod,
    RerankStrategy,
    SearchQuery,
    SearchResult,
    SearchResults,
)


class SearchManager:
    def __init__(self, *, index_backend: KBIndexBackend, config: KBConfig) -> None:
        self.index = index_backend
        self.config = config

    async def search(self, *, query: SearchQuery) -> SearchResults:
        targets_stats: List[ExplainTargetStat] = []
        norm_ranges: Dict[str, Tuple[float, float]] = {}
        t0 = time.perf_counter()
        trace_id = str(uuid.uuid4())

        if len(query.targets) <= 1:
            t_bt0 = time.perf_counter()
            initial_results = await self.index.search(query=query)
            t_bt1 = time.perf_counter()
            tgt = query.targets[0]
            targets_stats.append(
                ExplainTargetStat(
                    table_name=tgt.table_name,
                    vector_column=tgt.vector_column,
                    weight=float(getattr(tgt, "weight", 1.0) or 1.0),
                    requested=query.limit,
                    returned=len(initial_results),
                    duration_ms=(t_bt1 - t_bt0) * 1000.0,
                )
            )
        else:
            initial_results, targets_stats, norm_ranges = await self._fanout_search(query)

        rerank_options = query.rerank
        if rerank_options.strategy == RerankStrategy.NONE or not self.config.plugins.rerankers:
            fusion_mode = query.hybrid.fusion_strategy if query.hybrid else FusionStrategy.LINEAR
            t1 = time.perf_counter()
            return SearchResults(
                results=initial_results,
                explain=ExplainData(
                    fusion=fusion_mode,
                    weighting=query.hybrid,
                    targets_used=targets_stats,
                    retrieval_counts={f"{s.table_name}.{s.vector_column}": s.returned for s in targets_stats},
                    timings_ms={
                        "total": (t1 - t0) * 1000.0,
                        **{f"t.{s.table_name}.{s.vector_column}": s.duration_ms for s in targets_stats},
                    },
                    normalization_method=NormalizationMethod.MINMAX,
                    trace_id=trace_id,
                ),
                search_duration_ms=(t1 - t0) * 1000.0,
            )

        reranker_id = rerank_options.model
        if not reranker_id:
            reranker_id = next(iter(self.config.plugins.rerankers.keys()), None)

        reranker = self.config.plugins.rerankers.get(reranker_id) if reranker_id else None
        if not reranker:
            fusion_mode = query.hybrid.fusion_strategy if query.hybrid else FusionStrategy.LINEAR
            t1 = time.perf_counter()
            return SearchResults(
                results=initial_results,
                explain=ExplainData(
                    fusion=fusion_mode,
                    weighting=query.hybrid,
                    targets_used=targets_stats,
                    retrieval_counts={f"{s.table_name}.{s.vector_column}": s.returned for s in targets_stats},
                    timings_ms={
                        "total": (t1 - t0) * 1000.0,
                        **{f"t.{s.table_name}.{s.vector_column}": s.duration_ms for s in targets_stats},
                    },
                    normalization_method=NormalizationMethod.MINMAX,
                    trace_id=trace_id,
                    notes=["No reranker found; returning initial results"],
                ),
                search_duration_ms=(t1 - t0) * 1000.0,
            )

        candidates = initial_results[: rerank_options.top_n]
        remainder = initial_results[rerank_options.top_n :]

        t_rrf0 = time.perf_counter()
        reranked_candidates = await reranker.rerank(results=candidates, query=query)
        t_rrf1 = time.perf_counter()

        final_results = reranked_candidates + remainder
        fusion_mode = query.hybrid.fusion_strategy if query.hybrid else FusionStrategy.LINEAR
        t1 = time.perf_counter()
        explain = ExplainData(
            fusion=fusion_mode,
            weighting=query.hybrid,
            targets_used=targets_stats,
            rerank_used=True,
            rerank_strategy=rerank_options.strategy,
            rerank_model=reranker_id,
            retrieval_counts={f"{s.table_name}.{s.vector_column}": s.returned for s in targets_stats},
            timings_ms={
                "total": (t1 - t0) * 1000.0,
                "rerank": (t_rrf1 - t_rrf0) * 1000.0,
                **{f"t.{s.table_name}.{s.vector_column}": s.duration_ms for s in targets_stats},
            },
            normalization_method=NormalizationMethod.MINMAX,
            trace_id=trace_id,
        )
        return SearchResults(
            results=final_results[: query.limit],
            explain=explain,
            search_duration_ms=(t1 - t0) * 1000.0,
        )

    async def _fanout_search(
        self, query: SearchQuery
    ) -> Tuple[List[SearchResult], List[ExplainTargetStat], Dict[str, Tuple[float, float]]]:
        fused: dict[str, float] = {}
        payload_by_id: dict[str, dict] = {}
        stats: List[ExplainTargetStat] = []
        norm_ranges: Dict[str, Tuple[float, float]] = {}

        for tgt in query.targets:
            subq = SearchQuery(
                text=query.text,
                targets=[tgt],
                hybrid=query.hybrid,
                filter=query.filter,
                aggregations=query.aggregations,
                expansion=query.expansion,
                rerank=query.rerank,
                rerank_candidates=query.rerank_candidates,
                limit=query.rerank_candidates or max(query.limit, 50),
                offset=0,
                highlight=query.highlight,
                explain=query.explain,
            )
            t_bt0 = time.perf_counter()
            results = await self.index.search(query=subq)
            t_bt1 = time.perf_counter()
            weight = float(getattr(tgt, "weight", 1.0) or 1.0)
            if results:
                svals = [r.score for r in results]
                smin, smax = min(svals), max(svals)
                norm_ranges_key = f"{tgt.table_name}.{tgt.vector_column}"
                norm_ranges[norm_ranges_key] = (smin, smax)
                for r in results:
                    if smax > smin:
                        norm = (r.score - smin) / (smax - smin)
                    else:
                        norm = 0.0
                    fused[r.chunk_id] = fused.get(r.chunk_id, 0.0) + weight * norm
                    payload_by_id.setdefault(r.chunk_id, r.payload)
            stats.append(
                ExplainTargetStat(
                    table_name=tgt.table_name,
                    vector_column=tgt.vector_column,
                    weight=weight,
                    requested=subq.limit,
                    returned=len(results),
                    duration_ms=(t_bt1 - t_bt0) * 1000.0,
                    norm_min=norm_ranges.get(f"{tgt.table_name}.{tgt.vector_column}", (None, None))[0],
                    norm_max=norm_ranges.get(f"{tgt.table_name}.{tgt.vector_column}", (None, None))[1],
                )
            )

        ranked = sorted(((score, cid) for cid, score in fused.items()), key=lambda t: t[0], reverse=True)
        top = ranked[query.offset : query.offset + query.limit]
        results = [SearchResult(chunk_id=cid, score=score, payload=payload_by_id.get(cid, {})) for score, cid in top]
        return results, stats, norm_ranges
