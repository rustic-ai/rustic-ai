from types import SimpleNamespace

from pydantic import ValidationError
import pytest
from uniko import IngestSource, Uniko

from rustic_ai.uniko_agent import (
    MemoryAgent,
    MemoryAgentConfig,
    MemoryScope,
    RecallRequest,
    RecallResponse,
)


def test_private_store_scope_must_be_explicit():
    assert MemoryScope(sessions=None).sessions is None
    assert MemoryScope(sessions=["user-1"]).sessions == ["user-1"]
    cases: list[dict[str, object]] = [{}, {"sessions": []}]
    for data in cases:
        with pytest.raises(ValidationError):
            MemoryScope.model_validate(data)


@pytest.mark.asyncio
async def test_real_ingested_document_recall_preserves_category_and_private_store():
    store = Uniko.builder().in_memory().build_sync()
    handle = store.agent("research")
    source_id = "rustic-memory:external_evidence:harbor-1"
    outcome = await handle.session("research-evidence").ingest(
        IngestSource.from_bytes(b"Harbor Project pilot budget is CAD 42000. Mina Patel coordinates it.")
        .with_mime("text/plain")
        .with_id(source_id)
    )
    assert outcome.chunk_node_ids
    memory = MemoryAgent.__new__(MemoryAgent)
    memory.config = MemoryAgentConfig()

    async def recall(handle, sessions, kinds):
        sent: list[RecallResponse] = []
        ctx = SimpleNamespace(
            payload=RecallRequest(
                query="Harbor Project pilot budget coordinator",
                scope=MemoryScope(sessions=sessions),
                allowed_record_kinds=kinds,
                item_limit=10,
                max_characters=6000,
            ),
            send=sent.append,
            get_context=lambda: {},
        )
        await MemoryAgent.recall_knowledge.__wfn__(memory, ctx, handle)
        assert len(sent) == 1
        return sent[0]

    scoped = await recall(handle, ["research-evidence"], ["external_evidence"])
    assert scoped.items
    assert not (await recall(handle, ["other-session"], ["external_evidence"])).items
    result = await recall(handle, None, ["external_evidence"])
    assert result.items
    assert "42000" in " ".join(item.content for item in result.items)
    assert source_id in [source for item in result.items for source in item.source_ids]
    assert not (await recall(handle, None, ["model_interpretation"])).items
    separate = Uniko.builder().in_memory().build_sync()
    assert not (await recall(separate.agent("other"), None, ["external_evidence"])).items
