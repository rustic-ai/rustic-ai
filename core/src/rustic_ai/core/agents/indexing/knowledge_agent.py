from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.core.guild import agent
from rustic_ai.core.guild.agent import Agent, ProcessContext
from rustic_ai.core.guild.agent_ext.depends.filesystem import FileSystem
from rustic_ai.core.guild.metaprog.agent_registry import AgentDependency
from rustic_ai.core.knowledgebase.agent_config import (
    KnowledgeAgentConfig,
    KnowledgeAgentProps,
)
from rustic_ai.core.knowledgebase.kbindex_backend import KBIndexBackend
from rustic_ai.core.knowledgebase.knol_manager import CatalogStatus, CatalogStatusFailed
from rustic_ai.core.knowledgebase.knowledge_base import KnowledgeBase
from rustic_ai.core.knowledgebase.model import Knol
from rustic_ai.core.knowledgebase.pipeline import PipelineSpec
from rustic_ai.core.knowledgebase.pipeline_executor import (
    ResolvedPipeline,
    SimplePipelineExecutor,
)
from rustic_ai.core.knowledgebase.query import (
    BoolFilter,
    HybridOptions,
    RerankOptions,
    SearchQuery,
    SearchResults,
)


class CatalogMediaLinks(BaseModel):
    media: List[MediaLink]


class CatalogMediaResults(BaseModel):
    results: List[CatalogStatus]


class IndexMediaLinks(BaseModel):
    media: List[MediaLink]


class IndexMediaResult(BaseModel):
    media_id: str
    knol_id: Optional[str] = None
    status: str = Field(description="indexed|failed")
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class IndexMediaResults(BaseModel):
    results: List[IndexMediaResult]


class KBTarget(BaseModel):
    table_name: str
    vector_column: str
    weight: float = 1.0


class KBSearchRequest(BaseModel):
    text: str
    targets: Optional[List[KBTarget]] = None
    limit: Optional[int] = None
    hybrid: Optional[HybridOptions] = None
    rerank: Optional[RerankOptions] = None
    filter: Optional[BoolFilter] = None
    explain: bool = False


class KBSearchResults(SearchResults):
    query_text: Optional[str] = None


class KnowledgeAgent(Agent[KnowledgeAgentProps]):
    """
    Agent that indexes MediaLink content into the KnowledgeBase and performs search.
    """

    def __init__(self, *args, **kwargs):
        self._kb: Optional[KnowledgeBase] = None
        self._target_to_pipeline: Dict[Tuple[str, str], ResolvedPipeline] = {}
        self._pipeline_specs_by_id: Dict[str, PipelineSpec] = {}
        self._cfg: Optional[KnowledgeAgentConfig] = None

    def _get_cfg(self) -> KnowledgeAgentConfig:
        if self._cfg is not None:
            return self._cfg
        try:
            props = self.config
            # Extract properties if available
            search_defaults = getattr(props, "search_defaults", None)
            chunking = getattr(props, "chunking", None)
            embedder = getattr(props, "embedder", None)

            self._cfg = KnowledgeAgentConfig.default_text(
                search_defaults=search_defaults,
                chunking=chunking,
                embedder=embedder,
            )
        except Exception:
            self._cfg = KnowledgeAgentConfig.default_text()
        return self._cfg

    async def _get_kb(self, *, filesystem: FileSystem, kb_backend: KBIndexBackend) -> KnowledgeBase:
        if self._kb is not None:
            return self._kb

        cfg = self._get_cfg()
        kb = KnowledgeBase(
            config=cfg.to_kb_config(),
            filesystem=filesystem,
            library_path=cfg.library_path,
            executor=SimplePipelineExecutor(),
            index_backend=kb_backend,
        )
        await kb.ensure_ready()

        # Resolve pipelines and build 1-1 target mapping: (table_name, vector_column) -> ResolvedPipeline
        spec_by_id: Dict[str, PipelineSpec] = {p.id: p for p in cfg.pipelines}
        bindings = [(p.id, p.storage.vector_column) for p in cfg.pipelines]
        resolved = kb.resolve_pipelines(bindings)

        target_map: Dict[Tuple[str, str], ResolvedPipeline] = {}
        for rp in resolved:
            p = spec_by_id[rp.id]
            table_name = p.resolve_storage_table(kb.schema)
            key = (table_name or "", p.storage.vector_column)
            if not table_name:
                raise ValueError(f"Pipeline {p.id} does not resolve to a table for schema routing")
            if key in target_map:
                raise ValueError(f"Duplicate pipeline mapping for target {key}")
            target_map[key] = rp

        # Validate embedder dimension matches schema vector dim
        for (tname, vcol), rp in target_map.items():
            table = next((t for t in kb.schema.tables if t.name == tname), None)
            if not table:
                raise ValueError(f"Table '{tname}' not found in schema")
            vs = next((vc for vc in table.vector_columns if vc.name == vcol), None)
            if not vs:
                raise ValueError(f"Vector column '{vcol}' not defined on table '{tname}'")
            dim = rp.embedder.get_dimension() if hasattr(rp.embedder, "get_dimension") else 0
            if dim and vs.dim != dim:
                raise ValueError(f"Embedder dimension {dim} != schema dim {vs.dim} for {tname}.{vcol}")

        self._kb = kb
        self._target_to_pipeline = target_map
        self._pipeline_specs_by_id = spec_by_id
        return kb

    @agent.processor(
        CatalogMediaLinks,
        depends_on=[
            AgentDependency(dependency_key="filesystem", guild_level=True),
            AgentDependency(dependency_key="kb_backend", guild_level=True),
        ],
    )
    async def catalog_media(
        self, ctx: ProcessContext[CatalogMediaLinks], filesystem: FileSystem, kb_backend: KBIndexBackend
    ):
        req = ctx.payload
        kb = await self._get_kb(filesystem=filesystem, kb_backend=kb_backend)
        out = await kb.catalog_media(req.media)
        ctx.send(CatalogMediaResults(results=out))

    @agent.processor(
        IndexMediaLinks,
        depends_on=[
            AgentDependency(dependency_key="filesystem", guild_level=True),
            AgentDependency(dependency_key="kb_backend", guild_level=True),
        ],
    )
    async def index_media(
        self, ctx: ProcessContext[IndexMediaLinks], filesystem: FileSystem, kb_backend: KBIndexBackend
    ):
        req = ctx.payload
        kb = await self._get_kb(filesystem=filesystem, kb_backend=kb_backend)
        # Delegate full flow to KB (catalog + route + ingest); return per-item status
        statuses = await kb.ingest_media(req.media)
        out: List[IndexMediaResult] = []
        for ml, st in zip(req.media, statuses):
            knol_obj = getattr(st, "knol", None)
            knol_id = knol_obj.id if isinstance(knol_obj, Knol) else None
            metadata = ml.metadata
            if isinstance(st, CatalogStatusFailed) or not knol_id:
                out.append(
                    IndexMediaResult(
                        media_id=ml.id, status="failed", error=getattr(st, "error", None), metadata=metadata
                    )
                )
            else:
                out.append(IndexMediaResult(media_id=ml.id, knol_id=knol_id, status="indexed", metadata=metadata))

        ctx.send(IndexMediaResults(results=out))

    @agent.processor(
        KBSearchRequest,
        depends_on=[
            AgentDependency(dependency_key="filesystem", guild_level=True),
            AgentDependency(dependency_key="kb_backend", guild_level=True),
        ],
    )
    async def search(self, ctx: ProcessContext[KBSearchRequest], filesystem: FileSystem, kb_backend: KBIndexBackend):
        req = ctx.payload
        cfg = self._get_cfg()
        kb = await self._get_kb(filesystem=filesystem, kb_backend=kb_backend)

        # Build targets and search via KnowledgeBase helpers
        pairs = [(t.table_name, t.vector_column) for t in req.targets] if req.targets else None
        targets = await kb.build_search_targets_from_text(text=req.text or "", targets=pairs)
        query = SearchQuery(
            text=req.text or "",
            targets=targets,
            hybrid=req.hybrid or cfg.search_defaults.hybrid,
            rerank=req.rerank or cfg.search_defaults.rerank or RerankOptions(),
            filter=req.filter,
            limit=req.limit or cfg.search_defaults.limit,
            offset=0,
            explain=bool(req.explain),
        )
        results = await kb.search(query=query)

        # Sanitize payloads to ensure JSON compatibility
        for res in results.results:
            for k, v in res.payload.items():
                if hasattr(v, "isoformat"):
                    res.payload[k] = v.isoformat()

        # Convert SearchResults to KBSearchResults and add query text
        kb_results = KBSearchResults(
            results=results.results,
            explain=results.explain,
            search_duration_ms=results.search_duration_ms,
            query_text=req.text,
        )
        ctx.send(kb_results)
