"""KnowledgeBase: wires KBConfig + filesystem + executor + index backend.

This class keeps responsibilities minimal:
- Storage preparation from KBSchema
- Resolving pipelines from KBConfig into concrete ResolvedPipeline instances
- Streaming execution (executor.rows_for_knol) into the KBIndex backend upsert
- Thin wrappers for search and deletes
"""

from typing import AsyncIterator, Dict, List, Sequence, Tuple

from fsspec.implementations.dirfs import DirFileSystem as FileSystem

from .config import KBConfig
from .kbindex_backend import KBIndexBackend
from .knol_utils import KnolUtils
from .model import Knol
from .pipeline_executor import EmittedRow, PipelineExecutor, ResolvedPipeline
from .query import (
    ExplainData,
    ExplainTargetStat,
    FusionStrategy,
    RerankStrategy,
    SearchQuery,
    SearchResult,
    SearchResults,
)


class KnowledgeBase:
    def __init__(
        self,
        *,
        config: KBConfig,
        filesystem: FileSystem,
        library_path: str,
        executor: PipelineExecutor,
        index_backend: KBIndexBackend,
    ) -> None:
        self.config = config
        self.filesystem = filesystem
        self.library_path = library_path
        self.executor = executor
        self.index = index_backend

    @property
    def schema(self):
        return self.config.kb_schema

    async def ensure_ready(self) -> None:
        await self.index.ensure_ready(schema=self.schema)

    def resolve_pipelines(self, bindings: Sequence[Tuple[str, str]]) -> List[ResolvedPipeline]:
        """Resolve pipeline ids to concrete pipelines with vector_space ids.

        Args:
            bindings: sequence of (pipeline_id, vector_space_id) pairs

        Returns:
            List of ResolvedPipeline instances
        """
        # Map pipeline id -> spec
        spec_by_id = {p.id: p for p in self.config.pipelines}
        out: List[ResolvedPipeline] = []
        for pid, vsid in bindings:
            p = spec_by_id.get(pid)
            if p is None:
                continue
            # Resolve plugins by logical id
            chunker = self.config.plugins.chunkers[p.chunker.chunker_id]
            embedder = self.config.plugins.embedders[p.embedder.embedder_id]
            projector = None
            if p.projector:
                projector = self.config.plugins.projectors[p.projector.projector_id]
            out.append(
                ResolvedPipeline(
                    id=p.id,
                    chunker_id=p.chunker.chunker_id,
                    policy_version=p.chunker.policy_version,
                    vector_space_id=vsid,
                    chunker=chunker,
                    embedder=embedder,
                    projector=projector,
                )
            )
        return out

    async def ingest_knol(self, *, knol: Knol, table_name: str, pipelines: Sequence[ResolvedPipeline]) -> None:
        async def _rows() -> AsyncIterator[EmittedRow]:
            async for row in self.executor.rows_for_knol(
                knol=knol, fs=self.filesystem, library_path=self.library_path, pipelines=pipelines
            ):
                yield row

        await self.index.upsert(table_name=table_name, rows=_rows())

    async def ingest_knol_id(self, *, knol_id: str, table_name: str, pipelines: Sequence[ResolvedPipeline]) -> None:
        knol = await KnolUtils.read_knol_from_library(self.filesystem, self.library_path, knol_id)
        await self.ingest_knol(knol=knol, table_name=table_name, pipelines=pipelines)

    async def delete_chunks(self, *, table_name: str, chunk_ids: Sequence[str]) -> None:
        await self.index.delete_by_chunk_ids(table_name=table_name, chunk_ids=list(chunk_ids))

    async def search(self, *, query: SearchQuery) -> SearchResults:
        # If single target, defer directly to backend
        targets_stats: List[ExplainTargetStat] = []
        norm_ranges: Dict[str, Tuple[float, float]] = {}
        if len(query.targets) <= 1:
            initial_results = await self.index.search(query=query)
        else:
            # Multi-target fanout with simple linear fusion and per-target weighting
            initial_results, targets_stats, norm_ranges = await self._fanout_search(query)

        # Apply reranking if configured
        rerank_options = query.rerank
        if rerank_options.strategy == RerankStrategy.NONE or not self.config.plugins.rerankers:
            fusion_mode = query.hybrid.fusion_strategy if query.hybrid else FusionStrategy.LINEAR
            return SearchResults(
                results=initial_results,
                explain=ExplainData(
                    fusion=fusion_mode,
                    weighting=query.hybrid,
                    targets_used=targets_stats,
                ),
            )

        reranker_id = rerank_options.model
        if not reranker_id:
            reranker_id = next(iter(self.config.plugins.rerankers.keys()), None)

        reranker = self.config.plugins.rerankers.get(reranker_id) if reranker_id else None
        if not reranker:
            fusion_mode = query.hybrid.fusion_strategy if query.hybrid else FusionStrategy.LINEAR
            return SearchResults(
                results=initial_results,
                explain=ExplainData(
                    fusion=fusion_mode,
                    weighting=query.hybrid,
                    targets_used=targets_stats,
                    notes=["No reranker found; returning initial results"],
                ),
            )

        # Rerank top N candidates
        candidates = initial_results[: rerank_options.top_n]
        remainder = initial_results[rerank_options.top_n :]

        reranked_candidates = await reranker.rerank(results=candidates, query=query)

        final_results = reranked_candidates + remainder
        fusion_mode = query.hybrid.fusion_strategy if query.hybrid else FusionStrategy.LINEAR
        explain = ExplainData(
            fusion=fusion_mode,
            weighting=query.hybrid,
            targets_used=targets_stats,
            rerank_used=True,
            rerank_strategy=rerank_options.strategy,
            rerank_model=reranker_id,
        )
        return SearchResults(results=final_results[: query.limit], explain=explain)

    async def _fanout_search(
        self, query: SearchQuery
    ) -> Tuple[List[SearchResult], List[ExplainTargetStat], Dict[str, Tuple[float, float]]]:
        """Multi-target fanout with simple linear fusion and per-target weighting."""
        fused: dict[str, float] = {}
        payload_by_id: dict[str, dict] = {}
        stats: List[ExplainTargetStat] = []
        norm_ranges: Dict[str, Tuple[float, float]] = {}

        # For each target, search with a single-target query clone
        for tgt in query.targets:
            subq = SearchQuery(
                text=query.text,
                vector=query.vector,
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
            results = await self.index.search(query=subq)
            weight = float(getattr(tgt, "weight", 1.0) or 1.0)
            # Min-max normalize per target for simple fusion stability
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
                )
            )

        # Materialize fused list
        ranked = sorted(((score, cid) for cid, score in fused.items()), key=lambda t: t[0], reverse=True)
        top = ranked[query.offset : query.offset + query.limit]
        results = [SearchResult(chunk_id=cid, score=score, payload=payload_by_id.get(cid, {})) for score, cid in top]
        return results, stats, norm_ranges
