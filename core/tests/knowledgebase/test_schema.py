from pydantic import ValidationError
import pytest

from rustic_ai.core.knowledgebase.schema import (
    ColumnSpec,
    IndexSpec,
    KBSchema,
    RoutingRule,
    RoutingSpec,
    TableMatch,
    TableSpec,
    VectorIndexSpec,
    VectorSpec,
)


def _minimal_text_table():
    return TableSpec(
        name="text_chunks",
        match=TableMatch(modality="text"),
        primary_key=["knol_id", "chunk_index"],
        columns=[
            ColumnSpec(name="knol_id", type="string", source="chunk", selector="knol_id", nullable=False),
            ColumnSpec(name="chunk_index", type="int", source="chunk", selector="index", nullable=False),
            ColumnSpec(name="text", type="text", source="chunk", selector="text"),
        ],
        vector_columns=[
            VectorSpec(name="embedding", dim=8, distance="cosine", index=VectorIndexSpec(type="hnsw", params={})),
        ],
        indexes=[IndexSpec(name="idx_text", kind="fulltext", columns=["text"], options={})],
    )


def test_schema_routing_precedence():
    schema = KBSchema(
        id="kb-mm-v1",
        version=1,
        backend_profile="generic",
        routing=RoutingSpec(
            rules=[
                RoutingRule(match=TableMatch(modality="text", mimetype="text/x-python"), table="text_python_chunks"),
                RoutingRule(match=TableMatch(modality="text", mimetype="text/*"), table="text_chunks"),
                RoutingRule(match=TableMatch(modality="image"), table="image_chunks"),
            ]
        ),
        tables=[
            _minimal_text_table(),
            TableSpec(
                name="text_python_chunks",
                match=TableMatch(modality="text", mimetype="text/x-python"),
                primary_key=["knol_id", "chunk_index"],
                columns=[
                    ColumnSpec(name="knol_id", type="string", source="chunk", selector="knol_id", nullable=False),
                    ColumnSpec(name="chunk_index", type="int", source="chunk", selector="index", nullable=False),
                    ColumnSpec(name="text", type="text", source="chunk", selector="text"),
                ],
            ),
            TableSpec(
                name="image_chunks",
                match=TableMatch(modality="image"),
                primary_key=["knol_id", "chunk_index"],
                columns=[
                    ColumnSpec(name="knol_id", type="string", source="chunk", selector="knol_id", nullable=False),
                    ColumnSpec(name="chunk_index", type="int", source="chunk", selector="index", nullable=False),
                ],
            ),
        ],
    )

    # exact mimetype wins over wildcard
    assert schema.routing.resolve_table("text", "text/x-python") == "text_python_chunks"
    # wildcard used when exact not present
    assert schema.routing.resolve_table("text", "text/plain") == "text_chunks"
    # modality match
    assert schema.routing.resolve_table("image", "image/png") == "image_chunks"
    # no match
    assert schema.routing.resolve_table("audio", "audio/wav") is None


def test_table_pk_and_index_validation():
    # missing pk column should raise
    with pytest.raises(ValidationError):
        TableSpec(
            name="bad_table",
            match=TableMatch(modality="text"),
            primary_key=["knol_id"],
            columns=[ColumnSpec(name="text", type="text", source="chunk", selector="text")],
        )

    # index column must exist (when identifier)
    with pytest.raises(ValidationError):
        TableSpec(
            name="bad_idx",
            match=TableMatch(modality="text"),
            primary_key=["knol_id"],
            columns=[
                ColumnSpec(name="knol_id", type="string", source="chunk", selector="knol_id", nullable=False),
            ],
            indexes=[IndexSpec(name="idx_missing", kind="btree", columns=["missing"], options={})],
        )


def test_vector_spec_validation():
    # dim must be > 0
    with pytest.raises(ValidationError):
        VectorSpec(name="emb", dim=0, distance="cosine", index=VectorIndexSpec(type="hnsw", params={}))
