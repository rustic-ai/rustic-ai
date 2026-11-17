"""Focused contract tests for the bounded MemoryAgent writer/reader API."""

from types import SimpleNamespace

from pydantic import ValidationError
import pytest

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.uniko_agent import (
    IngestDocumentRequest,
    MemoryAgent,
    MemoryRecordKind,
    MemoryScope,
    RecallRequest,
    RecordMemoryRequest,
)


def test_recall_requires_explicit_scope_categories_and_bounds():
    request = RecallRequest(
        query="customer preferences",
        scope=MemoryScope(sessions=["customer-1"]),
        allowed_record_kinds=[MemoryRecordKind.USER_ASSERTION],
        item_limit=7,
        max_characters=1200,
    )

    assert request.scope.sessions == ["customer-1"]
    assert request.allowed_record_kinds == [MemoryRecordKind.USER_ASSERTION]
    assert request.item_limit == 7
    assert request.max_characters == 1200

    with pytest.raises(ValidationError):
        RecallRequest(query="unscoped")
    with pytest.raises(ValidationError):
        RecallRequest(
            query="unbounded categories",
            scope=MemoryScope(sessions=["customer-1"]),
            allowed_record_kinds=[],
        )


@pytest.mark.asyncio
async def test_non_filesystem_media_and_legacy_sources_are_rejected():
    external = MediaLink(
        url="uploads/sales.csv",
        name="sales.csv",
        mimetype="text/csv",
        on_filesystem=False,
    )
    errors = []
    memory = SimpleNamespace(_send_failure=lambda ctx, code: errors.append(code))
    ctx = SimpleNamespace(
        payload=IngestDocumentRequest(
            record_id="evidence-1",
            session_id="research",
            media_link=external,
        )
    )
    await MemoryAgent.ingest_document.__wfn__(memory, ctx, None, None, None)
    assert errors == ["document_rejected"]

    with pytest.raises(ValidationError):
        IngestDocumentRequest.model_validate(
            {
                "record_id": "evidence-1",
                "session_id": "research",
                "source_spec": {"path": "/tmp/private.csv"},
            }
        )


def test_stable_record_identifiers_and_categories_are_validated():
    request = RecordMemoryRequest(
        record_id="request-42:dataset-profile",
        session_id="analysis-user-7",
        sender_id="dataset_profiler",
        kind=MemoryRecordKind.DETERMINISTIC_OBSERVATION,
        content="rows=20, columns=4",
    )

    assert MemoryAgent._record_key(request.kind, request.record_id) == (
        "rustic-memory:deterministic_observation:request-42:dataset-profile"
    )

    with pytest.raises(ValidationError):
        request.model_copy(update={"record_id": "../../escape"}).__class__.model_validate(
            {**request.model_dump(), "record_id": "../../escape"}
        )


def test_recall_serialization_recovers_application_provenance():
    native = SimpleNamespace(
        node_id=1,
        kind="artifact_chunk",
        score=0.9,
        content="bounded profile",
        sources=[
            SimpleNamespace(
                kind="artifact",
                message_id=None,
                artifact_id="rustic-memory:deterministic_observation:profile-1",
                chunk_id="chunk-1",
            )
        ],
    )

    serialized = MemoryAgent._serialize_recall_item(MemoryAgent.__new__(MemoryAgent), native)

    assert serialized is not None
    assert serialized.record_kind == MemoryRecordKind.DETERMINISTIC_OBSERVATION
    assert serialized.sources[0]["artifact_id"].endswith("profile-1")


def test_untyped_uniko_items_are_explicitly_unknown():
    native = SimpleNamespace(
        node_id=1,
        kind="fact",
        score=0.9,
        content="consolidated content without application provenance",
        sources=[
            SimpleNamespace(
                kind="fact",
                message_id="legacy-message",
                artifact_id=None,
                chunk_id=None,
            )
        ],
    )

    assert (
        MemoryAgent._serialize_recall_item(MemoryAgent.__new__(MemoryAgent), native).record_kind
        == MemoryRecordKind.UNKNOWN
    )


def test_source_less_finalized_turn_recovers_category_and_record_id_from_envelope():
    native = SimpleNamespace(
        node_id=2,
        kind="chunk",
        score=0.8,
        content=(
            "user-1: Memory record type: user_assertion\n"
            "Record ID: request-42:user\n"
            "Source: user-1\n\n"
            "The visible assertion"
        ),
        sources=[],
    )

    serialized = MemoryAgent._serialize_recall_item(MemoryAgent.__new__(MemoryAgent), native)

    assert serialized is not None
    assert serialized.record_kind == MemoryRecordKind.USER_ASSERTION
    assert serialized.source_ids == ["request-42:user"]
    assert serialized.content == "The visible assertion"
