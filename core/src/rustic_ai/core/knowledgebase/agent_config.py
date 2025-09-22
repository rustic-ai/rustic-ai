from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

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
from rustic_ai.core.knowledgebase.query import HybridOptions
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
    explain: bool = False


class KnowledgeAgentConfig(BaseModel):
    """Configuration for KnowledgeAgent built on top of KBConfig with SchemaInfer.

    This exposes SchemaInfer inputs and plugin/pipeline selections with sensible defaults.
    """

    library_path: str = Field(default="library")
    backend_profile: str = Field(default="memory")

    # Core KB pieces
    schema_infer: SchemaInferConfig
    plugins: PluginRegistry
    pipelines: List[PipelineSpec]

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
    def default_text(id: str = "kb_default") -> "KnowledgeAgentConfig":
        # Plugins (instances)
        chunker = SimpleTextChunker(id="text_chunker", chunk_size=4000, chunk_overlap=200)
        embedder = FeatureHashingTextEmbedder(id="text_embedder", dimension=1024, distance="cosine", normalize=True)

        plugins = PluginRegistry(
            chunkers={"text_chunker": chunker},
            embedders={"text_embedder": embedder},
            projectors={},
            rerankers={},
        )

        # SchemaInfer: one vector column for text
        vname = "v_text_1024"
        vector_spec = VectorSpec(name=vname, dim=1024, distance="cosine", index=VectorIndexSpec(type="hnsw"))

        modalities: Dict[Modality, ModalitySpec] = {
            Modality.TEXT: ModalitySpec(
                enabled=True,
                specialized_mimetypes=[],
                vectors=[vector_spec],
            )
        }

        schema_infer = SchemaInferConfig(
            kb=KBIdentity(id=id, backend_profile="memory"),
            modalities=modalities,
        )

        # Pipelines: 1-1 target ↔ pipeline
        pipeline = PipelineSpec(
            id="text_pipeline",
            schema_ref=SchemaRef(schema_id=id, schema_version=1),
            target=TargetSelector(modality=Modality.TEXT, mimetype="text/*"),
            chunker=ChunkerRef(chunker_id="text_chunker", policy_version="v1"),
            embedder=EmbedderRef(embedder_id="text_embedder", embedder_version="v1"),
            storage=StorageSpec(vector_column=vname),
        )

        return KnowledgeAgentConfig(
            library_path="library",
            backend_profile="memory",
            schema_infer=schema_infer,
            plugins=plugins,
            pipelines=[pipeline],
            search_defaults=SearchDefaults(),
        )
