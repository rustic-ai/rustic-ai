from typing import AsyncIterator, Dict, List, Optional, Sequence, Tuple

from fsspec.implementations.dirfs import DirFileSystem as FileSystem

from rustic_ai.core.agents.commons import MediaLink

from .chunks import TextChunk
from .config import KBConfig
from .kbindex_backend import KBIndexBackend
from .knol_manager import CatalogStatus, CatalogStatusFailed, KnolManager
from .knol_utils import KnolUtils
from .model import Knol
from .pipeline_executor import EmittedRow, PipelineExecutor, ResolvedPipeline
from .query import BoolFilter, HybridOptions, SearchQuery, SearchResults, SearchTarget
from .search_manager import SearchManager


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
        self._search_manager = SearchManager(index_backend=index_backend, config=config)
        self._knol_manager = KnolManager(filesystem, location=library_path)
        self._target_to_pipeline: Dict[Tuple[str, str], ResolvedPipeline] = {}

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

    def resolve_target_pipeline_map(self) -> Dict[Tuple[str, str], ResolvedPipeline]:
        if self._target_to_pipeline:
            return self._target_to_pipeline
        # Bind pipelines (id -> own storage vector column)
        bindings = [(p.id, p.storage.vector_column) for p in self.config.pipelines]
        resolved = self.resolve_pipelines(bindings)
        spec_by_id = {p.id: p for p in self.config.pipelines}
        target_map: Dict[Tuple[str, str], ResolvedPipeline] = {}
        for rp in resolved:
            p = spec_by_id[rp.id]
            table_name = p.resolve_storage_table(self.schema)
            if not table_name:
                continue
            key = (table_name, p.storage.vector_column)
            if key in target_map:
                raise ValueError(f"Duplicate pipeline mapping for target {key}")
            target_map[key] = rp
        self._target_to_pipeline = target_map
        return target_map

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
        return await self._search_manager.search(query=query)

    async def catalog_media(self, media: List[MediaLink]) -> List[CatalogStatus]:
        km = self._knol_manager
        out: List[CatalogStatus] = []
        for ml in media:
            try:
                status = await km.catalog_medialink(ml)
                out.append(status)
            except Exception as e:  # pragma: no cover
                out.append(CatalogStatusFailed(error=str(e), action="catalog"))
        return out

    async def ingest_media(self, media: List[MediaLink]) -> List[CatalogStatus]:
        statuses = await self.catalog_media(media)
        target_map = self.resolve_target_pipeline_map()
        for st in statuses:
            knol = getattr(st, "knol", None)
            if not knol:
                continue
            major = (knol.mimetype or "").split("/", 1)[0] if knol.mimetype else None
            table = self.schema.routing.resolve_table(major, knol.mimetype)
            if not table and target_map:
                table = next(iter({t[0] for t in target_map.keys()}), None)
            if not table:
                continue
            candidates = [(t, rp) for t, rp in target_map.items() if t[0] == table]
            if not candidates:
                continue
            (table_name, _), rp = candidates[0]
            await self.ingest_knol(knol=knol, table_name=table_name, pipelines=[rp])
        return statuses

    async def build_search_targets_from_text(
        self,
        *,
        text: str,
        targets: Optional[List[Tuple[str, str]]] = None,
        library_path: Optional[str] = None,
    ) -> List[SearchTarget]:
        target_map = self.resolve_target_pipeline_map()
        pairs = targets or list(target_map.keys())
        q_bytes = (text or "").encode("utf-8", errors="ignore")
        out: List[SearchTarget] = []
        for i, (table_name, vector_column) in enumerate(pairs):
            rp = target_map.get((table_name, vector_column))
            if not rp:
                # fallback: any pipeline for the table
                cand = [(t, p) for t, p in target_map.items() if t[0] == table_name]
                if not cand:
                    continue
                (table_name, vector_column), rp = cand[0]
            q_chunk = TextChunk(
                id=f"query:{i}",
                knol_id="query",
                index=i,
                producer_id="query",
                content_bytes=q_bytes,
                encoding="utf-8",
                mimetype="text/plain",
            )
            qvec = await rp.embedder.embed(q_chunk, fs=self.filesystem, library_path=library_path or self.library_path)
            out.append(
                SearchTarget(
                    table_name=table_name,
                    vector_column=vector_column,
                    weight=1.0,
                    query_vector=[float(x) for x in qvec],
                )
            )
        return out

    async def search_text(
        self,
        *,
        text: str,
        targets: Optional[List[Tuple[str, str]]] = None,
        limit: int = 10,
        hybrid: Optional[HybridOptions] = None,
        filter: Optional[BoolFilter] = None,
        explain: bool = False,
    ) -> SearchResults:
        built_targets = await self.build_search_targets_from_text(text=text, targets=targets)
        q = SearchQuery(
            text=text, targets=built_targets, hybrid=hybrid, filter=filter, limit=limit, offset=0, explain=explain
        )
        return await self.search(query=q)
