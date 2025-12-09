from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from rustic_ai.core.guild.dsl import BaseAgentProps
from rustic_ai.core.knowledgebase.chunkers.simple_text import SimpleTextChunker
from rustic_ai.core.knowledgebase.config import KBConfig, PluginRegistry
from rustic_ai.core.knowledgebase.embedders.feature_hash_text import (
    FeatureHashingTextEmbedder,
)
from rustic_ai.core.knowledgebase.pipeline import (
    ChunkerRef,
    EmbedderRef,
    PipelineSpec,
    SchemaRef,
    StorageSpec,
    TargetSelector,
)
from rustic_ai.core.knowledgebase.query import HybridOptions, RerankOptions
from rustic_ai.core.knowledgebase.schema import VectorIndexSpec, VectorSpec
from rustic_ai.core.knowledgebase.schema_infer import (
    KBIdentity,
    Modality,
    ModalitySpec,
    SchemaInferConfig,
)


class SearchDefaults(BaseModel):
    limit: int = 10
    hybrid: Optional[HybridOptions] = Field(default=HybridOptions(dense_weight=0.5, sparse_weight=0.5))
    rerank: Optional[RerankOptions] = None
    explain: bool = False


class ChunkingDefaults(BaseModel):
    chunk_size: int = 4000
    chunk_overlap: int = 200


class EmbedderDefaults(BaseModel):
    dimension: int = 1024
    use_sign_hash: bool = True
    use_tf_log: bool = True


class KnowledgeAgentProps(BaseAgentProps):  # type: ignore
    """Serializable properties for KnowledgeAgent.

    This is the type used in AgentSpec[KnowledgeAgentProps].
    Only contains JSON-serializable configuration.
    """

    search_defaults: SearchDefaults = Field(default_factory=SearchDefaults)
    chunking: ChunkingDefaults = Field(default_factory=ChunkingDefaults)
    embedder: EmbedderDefaults = Field(default_factory=EmbedderDefaults)


def _default_plugins(
    chunking: Optional[ChunkingDefaults] = None, embedder: Optional[EmbedderDefaults] = None
) -> PluginRegistry:
    c_def = chunking or ChunkingDefaults()
    e_def = embedder or EmbedderDefaults()

    chunker = SimpleTextChunker(id="text_chunker", chunk_size=c_def.chunk_size, chunk_overlap=c_def.chunk_overlap)
    embedder_plugin = FeatureHashingTextEmbedder(
        id="text_embedder",
        dimension=e_def.dimension,
        use_sign_hash=e_def.use_sign_hash,
        use_tf_log=e_def.use_tf_log,
        distance="cosine",
        normalize=True,
    )

    return PluginRegistry(
        chunkers={"text_chunker": chunker},
        embedders={"text_embedder": embedder_plugin},
        projectors={},
        rerankers={},
    )


def _default_schema_infer(id: str = "kb_default", dimension: int = 1024) -> SchemaInferConfig:
    # SchemaInfer: one vector column for text
    vname = f"v_text_{dimension}"
    vector_spec = VectorSpec(name=vname, dim=dimension, distance="cosine", index=VectorIndexSpec(type="hnsw"))

    modalities: Dict[Modality, ModalitySpec] = {
        Modality.TEXT: ModalitySpec(
            enabled=True,
            specialized_mimetypes=[],
            vectors=[vector_spec],
        )
    }

    return SchemaInferConfig(
        kb=KBIdentity(id=id, backend_profile="memory"),
        modalities=modalities,
    )


def _default_pipelines(id: str = "kb_default", dimension: int = 1024) -> List[PipelineSpec]:
    vname = f"v_text_{dimension}"
    # Pipelines: 1-1 target ↔ pipeline
    pipeline = PipelineSpec(
        id="text_pipeline",
        schema_ref=SchemaRef(schema_id=id, schema_version=1),
        target=TargetSelector(modality=Modality.TEXT, mimetype="text/*"),
        chunker=ChunkerRef(chunker_id="text_chunker", policy_version="v1"),
        embedder=EmbedderRef(embedder_id="text_embedder", embedder_version="v1"),
        storage=StorageSpec(vector_column=vname),
    )
    return [pipeline]


class KnowledgeAgentConfig(BaseModel):
    """Configuration for KnowledgeAgent built on top of KBConfig with SchemaInfer.

    This exposes SchemaInfer inputs and plugin/pipeline selections with sensible defaults.
    This is NOT the AgentSpec properties type - use KnowledgeAgentProps for that.
    """

    library_path: str = Field(default="library")
    backend_profile: str = Field(default="memory")

    # Core KB pieces
    schema_infer: SchemaInferConfig = Field(default_factory=_default_schema_infer)
    plugins: PluginRegistry = Field(default_factory=_default_plugins)
    pipelines: List[PipelineSpec] = Field(default_factory=_default_pipelines)

    # Search behavior
    search_defaults: SearchDefaults = Field(default_factory=SearchDefaults)

    def to_kb_config(self) -> KBConfig:
        # Leverage KBConfig's pre-validator that converts schema_infer -> schema
        return KBConfig(
            schema_infer=self.schema_infer,
            plugins=self.plugins,
            pipelines=self.pipelines,
            id=self.schema_infer.kb.id,
            version=1,
            description=self.schema_infer.kb.description,
        )

    @staticmethod
    def default_text(
        id: str = "kb_default",
        chunking: Optional[ChunkingDefaults] = None,
        embedder: Optional[EmbedderDefaults] = None,
        search_defaults: Optional[SearchDefaults] = None,
    ) -> "KnowledgeAgentConfig":
        e_def = embedder or EmbedderDefaults()
        return KnowledgeAgentConfig(
            library_path="library",
            backend_profile="memory",
            schema_infer=_default_schema_infer(id, dimension=e_def.dimension),
            plugins=_default_plugins(chunking, embedder),
            pipelines=_default_pipelines(id, dimension=e_def.dimension),
            search_defaults=search_defaults or SearchDefaults(),
        )
