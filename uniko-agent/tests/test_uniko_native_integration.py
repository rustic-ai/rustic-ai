"""Native integration checks against the supported Uniko wheel."""

import gc

import uniko
from uniko import Scope, Turn

from rustic_ai.uniko_agent import MemoryAgent, MemoryRecordKind


def test_typed_turn_is_idempotent_scoped_persistent_and_deletable(tmp_path):
    database = tmp_path / "memory.db"
    record_id = "request-1:user"
    stored_id = MemoryAgent._record_key(MemoryRecordKind.USER_ASSERTION, record_id)
    stored_text = MemoryAgent._record_text(
        MemoryRecordKind.USER_ASSERTION,
        record_id,
        "user-1",
        "My preferred database is PostgreSQL.",
    )

    first = uniko.Uniko.open_sync(str(database))
    first_agent = first.agent("memory-agent")
    first_session = first_agent.session("user-session")
    first_session.observe_sync(Turn("user-1", stored_text).id(stored_id))
    first_session.observe_sync(Turn("user-1", stored_text).id(stored_id))
    report = first_session.finalize_sync()
    first_bundle = first_agent.recall_in_sync(
        "preferred database",
        Scope().sessions(["user-session"]),
    )
    serialized = [
        item
        for native in first_bundle.items
        if (item := MemoryAgent._serialize_recall_item(MemoryAgent.__new__(MemoryAgent), native)) is not None
    ]

    assert report.transcript_chunks
    assert serialized
    assert {item.content for item in serialized} == {"My preferred database is PostgreSQL."}
    assert all(item.record_kind == MemoryRecordKind.USER_ASSERTION for item in serialized)
    assert all(record_id in item.source_ids for item in serialized)
    del first_bundle, first_session, first_agent
    gc.collect()
    first.shutdown_sync()

    reopened = uniko.Uniko.open_sync(str(database))
    reopened_agent = reopened.agent("memory-agent")
    persisted = reopened_agent.recall_in_sync(
        "preferred database",
        Scope().sessions(["user-session"]),
    )
    persisted_items = [
        item
        for native in persisted.items
        if (item := MemoryAgent._serialize_recall_item(MemoryAgent.__new__(MemoryAgent), native)) is not None
    ]
    assert persisted_items

    reopened_agent.delete_session_sync("user-session")
    after_delete = reopened_agent.recall_in_sync(
        "preferred database",
        Scope().sessions(["user-session"]),
    )
    assert not after_delete.items
    del after_delete, persisted, reopened_agent
    gc.collect()
    reopened.shutdown_sync()
