from typing import Optional

from rustic_ai.core.knowledgebase.chunks import TextChunk
from rustic_ai.core.knowledgebase.model import Modality
from rustic_ai.core.knowledgebase.schema import VectorIndexSpec, VectorSpec
from rustic_ai.core.knowledgebase.schema_infer import (
    DefaultsPolicy,
    IndexPolicy,
    KBIdentity,
    KeyPolicy,
    ModalitySpec,
    NamingPolicy,
    SchemaInferConfig,
    infer_kb_schema,
)


def test_infer_kb_schema_text_with_specialized_mimetype():
    cfg = SchemaInferConfig(
        kb=KBIdentity(id="kb-auto", backend_profile="generic"),
        modalities={
            Modality.TEXT: ModalitySpec(specialized_mimetypes=["text/markdown"]),
        },
        defaults=DefaultsPolicy(
            indexes=IndexPolicy(
                btree_on=["knol_id", "chunk_created_at", "producer_id"],
                fulltext_on_text=True,
                fulltext_on_metadata=True,
            )
        ),
    )
    schema = infer_kb_schema(cfg)

    # Tables created
    table_names = {t.name for t in schema.tables}
    assert "chunks_text" in table_names
    assert "chunks_text__text_markdown" in table_names

    # Routing order: specialized first, then fallback
    # Ensure a specialized rule exists and a fallback rule exists
    assert any(r.match.modality == "text" and r.match.mimetype == "text/markdown" for r in schema.routing.rules)
    assert any(r.match.modality == "text" and r.match.mimetype == "text/*" for r in schema.routing.rules)

    # Columns include knol fields, chunk fields, computed text, metadata json, and common meta
    text_table = next(t for t in schema.tables if t.name == "chunks_text")
    colnames = {c.name for c in text_table.columns}
    assert {
        "knol_id",
        "chunk_index",
        "text",
        "metadata",
        "knol_name",
        "chunk_id",
        "chunk_kind",
        "chunk_created_at",
        "chunk_updated_at",
    }.issubset(colnames)
    assert {"author", "tags"}.issubset(colnames)  # from CommonMetaPart

    # Indexes include FTS on text and metadata
    assert any(i.kind == "fulltext" and i.columns == ["text"] for i in text_table.indexes)
    assert any(i.kind == "fulltext" and i.columns == ["metadata"] for i in text_table.indexes)


def test_include_text_toggle_and_indexing():
    cfg = SchemaInferConfig(
        kb=KBIdentity(id="kb-auto"),
        modalities={
            Modality.TEXT: ModalitySpec(
                specialized_mimetypes=[],
                include_text_column=False,  # override to disable
            ),
        },
    )
    schema = infer_kb_schema(cfg)
    t = next(t for t in schema.tables if t.name == "chunks_text")
    cols = {c.name for c in t.columns}
    assert "text" not in cols
    # Should not create a fulltext index on text if column missing
    assert not any(i.kind == "fulltext" and i.columns == ["text"] for i in t.indexes)


def test_meta_column_custom_name_and_index():
    cfg = SchemaInferConfig(
        kb=KBIdentity(id="kb-auto"),
        modalities={
            Modality.TEXT: ModalitySpec(),
        },
        defaults=DefaultsPolicy(),
    )
    # Use per-modality override for meta column name via defaults replacement
    cfg.defaults.meta_column = "meta_json"
    schema = infer_kb_schema(cfg)
    t = next(t for t in schema.tables if t.name == "chunks_text")
    cols = {c.name for c in t.columns}
    assert "meta_json" in cols
    assert any(i.kind == "fulltext" and i.columns == ["meta_json"] for i in t.indexes)


def test_naming_policy_sanitization_and_templates():
    def sanitize(m: str) -> str:
        return m.replace("/", "__")

    cfg = SchemaInferConfig(
        kb=KBIdentity(id="kb-auto"),
        modalities={
            Modality.TEXT: ModalitySpec(specialized_mimetypes=["text/markdown"]),
        },
        naming=NamingPolicy(
            default_table_template="kb_{modality}",
            specialized_table_template="kb_{modality}__{mimetype}",
            sanitize_mimetype=sanitize,
        ),
    )
    schema = infer_kb_schema(cfg)
    table_names = {t.name for t in schema.tables}
    assert "kb_text" in table_names
    assert "kb_text__text__markdown" in table_names


def test_keys_and_indexes_policy_overrides():
    cfg = SchemaInferConfig(
        kb=KBIdentity(id="kb-auto"),
        modalities={
            Modality.TEXT: ModalitySpec(
                keys=KeyPolicy(primary_key=["chunk_id"], unique=[["knol_id", "chunk_index"]]),
                indexes=IndexPolicy(btree_on=["knol_id"], fulltext_on_text=False, fulltext_on_metadata=True),
            )
        },
    )
    schema = infer_kb_schema(cfg)
    t = next(t for t in schema.tables if t.name == "chunks_text")
    assert t.primary_key == ["chunk_id"]
    assert ["knol_id", "chunk_index"] in t.unique
    # text FTS disabled
    assert not any(i.kind == "fulltext" and i.columns == ["text"] for i in t.indexes)
    # metadata FTS enabled (default column name)
    assert any(i.kind == "fulltext" and i.columns == ["metadata"] for i in t.indexes)


def test_vectors_attached_per_modality():
    vecs = [VectorSpec(name="v1", dim=8, distance="cosine", index=VectorIndexSpec(type="hnsw", params={}))]
    cfg = SchemaInferConfig(
        kb=KBIdentity(id="kb-auto"),
        modalities={
            Modality.TEXT: ModalitySpec(vectors=vecs),
        },
    )
    schema = infer_kb_schema(cfg)
    t = next(t for t in schema.tables if t.name == "chunks_text")
    assert any(v.name == "v1" and v.dim == 8 for v in t.vector_columns)


def test_custom_chunk_class_reflection():
    class MyTextChunk(TextChunk):
        # add a new optional field
        foo_bar: Optional[int] = None

    cfg = SchemaInferConfig(
        kb=KBIdentity(id="kb-auto"),
        modalities={Modality.TEXT: ModalitySpec()},
        chunk_class_for_modality={Modality.TEXT: MyTextChunk},
    )
    schema = infer_kb_schema(cfg)
    t = next(t for t in schema.tables if t.name == "chunks_text")
    cols = {c.name for c in t.columns}
    assert "foo_bar" in cols


def test_multiple_modalities_and_routing_precedence():
    cfg = SchemaInferConfig(
        kb=KBIdentity(id="kb-auto"),
        modalities={
            Modality.TEXT: ModalitySpec(specialized_mimetypes=["text/markdown", "text/html"]),
            Modality.IMAGE: ModalitySpec(specialized_mimetypes=["image/png"]),
        },
    )
    schema = infer_kb_schema(cfg)
    # Specialized rules should appear before fallbacks
    text_rules = [r for r in schema.routing.rules if r.match.modality == "text"]
    spec_positions = [i for i, r in enumerate(text_rules) if r.match.mimetype in {"text/markdown", "text/html"}]
    fallback_position = next(i for i, r in enumerate(text_rules) if r.match.mimetype == "text/*")
    assert spec_positions and min(spec_positions) < fallback_position

    image_rules = [r for r in schema.routing.rules if r.match.modality == "image"]
    spec_pos_img = next(i for i, r in enumerate(image_rules) if r.match.mimetype == "image/png")
    fallback_pos_img = next(i for i, r in enumerate(image_rules) if r.match.mimetype == "image/*")
    assert spec_pos_img < fallback_pos_img


def test_denormalize_meta_disable_keeps_json_only():
    cfg = SchemaInferConfig(
        kb=KBIdentity(id="kb-auto"),
        modalities={
            Modality.IMAGE: ModalitySpec(denormalize_meta_fields=False),
        },
    )
    schema = infer_kb_schema(cfg)
    t = next(t for t in schema.tables if t.name == "chunks_image")
    cols = {c.name for c in t.columns}
    # meta json present
    assert "metadata" in cols
    # common meta fields should not be present when denormalization disabled
    assert not {"author", "tags"}.intersection(cols)


def test_table_name_override_per_modality():
    cfg = SchemaInferConfig(
        kb=KBIdentity(id="kb-auto"),
        modalities={
            Modality.IMAGE: ModalitySpec(table_name="kbimg"),
        },
    )
    schema = infer_kb_schema(cfg)
    assert any(t.name == "kbimg" for t in schema.tables)
