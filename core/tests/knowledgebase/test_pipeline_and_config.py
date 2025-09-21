from pydantic import ValidationError
import pytest

from rustic_ai.core.knowledgebase.config import KBConfig, PluginRegistry
from rustic_ai.core.knowledgebase.pipeline import (
    ChunkerRef,
    EmbedderRef,
    PipelineSpec,
    ProjectorRef,
    SchemaRef,
    StorageSpec,
    TargetSelector,
)
from rustic_ai.core.knowledgebase.schema import (
    ColumnSpec,
    KBSchema,
    RoutingRule,
    RoutingSpec,
    TableMatch,
    TableSpec,
    VectorIndexSpec,
    VectorSpec,
)


def _schema_text_only():
    return KBSchema(
        id="kb-mm-v1",
        version=1,
        backend_profile="generic",
        routing=RoutingSpec(
            rules=[RoutingRule(match=TableMatch(modality="text", mimetype="text/*"), table="text_chunks")]
        ),
        tables=[
            TableSpec(
                name="text_chunks",
                match=TableMatch(modality="text"),
                primary_key=["knol_id", "chunk_index"],
                columns=[
                    ColumnSpec(name="knol_id", type="string", source="chunk", selector="knol_id", nullable=False),
                    ColumnSpec(name="chunk_index", type="int", source="chunk", selector="index", nullable=False),
                    ColumnSpec(name="text", type="text", source="chunk", selector="text"),
                ],
                vector_columns=[
                    VectorSpec(
                        name="embedding", dim=8, distance="cosine", index=VectorIndexSpec(type="hnsw", params={})
                    ),
                ],
            )
        ],
    )


def test_pipeline_resolve_and_validate():
    schema = _schema_text_only()
    pipe = PipelineSpec(
        id="pipe-text",
        schema_ref=SchemaRef(schema_id=schema.id, schema_version=schema.version),
        target=TargetSelector(modality="text", mimetype="text/plain"),
        chunker=ChunkerRef(chunker_id="default", policy_version="v1"),
        embedder=EmbedderRef(embedder_id="text-emb", embedder_version="v1"),
        storage=StorageSpec(vector_column="embedding"),
    )

    # resolve table from routing
    assert pipe.resolve_storage_table(schema) == "text_chunks"
    # validate vector column exists
    pipe.validate_against_schema(schema)


def test_pipeline_projection_validation():
    schema = _schema_text_only()
    # invalid projection target mimetype
    with pytest.raises(ValidationError):
        PipelineSpec(
            id="pipe-img",
            schema_ref=SchemaRef(schema_id=schema.id, schema_version=schema.version),
            target=TargetSelector(modality="image", mimetype="image/*"),
            chunker=ChunkerRef(chunker_id="default", policy_version="v1"),
            projector=ProjectorRef(
                projector_id="ocr", projector_version="v1", target_modality="text", target_mimetype="image/png"
            ),
            embedder=EmbedderRef(embedder_id="text-emb", embedder_version="v1"),
            storage=StorageSpec(vector_column="embedding"),
        )


def test_kbconfig_plugin_coercion_and_refs():
    schema = _schema_text_only()
    cfg = KBConfig(
        id="kb",
        schema=schema,
        plugins=PluginRegistry(
            chunkers={"default": {"id": "default", "kind": "rustic_ai.core.knowledgebase.plugins.ChunkerPlugin"}},
            projectors={},
            embedders={"text-emb": {"id": "text-emb", "kind": "rustic_ai.core.knowledgebase.plugins.EmbedderPlugin"}},
        ),
        pipelines=[
            PipelineSpec(
                id="pipe-text",
                schema_ref=SchemaRef(schema_id=schema.id, schema_version=schema.version),
                target=TargetSelector(modality="text", mimetype="text/plain"),
                chunker=ChunkerRef(chunker_id="default", policy_version="v1"),
                embedder=EmbedderRef(embedder_id="text-emb", embedder_version="v1"),
                storage=StorageSpec(vector_column="embedding"),
            )
        ],
    )

    # coercion should produce instances
    assert "default" in cfg.plugins.chunkers
    assert "text-emb" in cfg.plugins.embedders
