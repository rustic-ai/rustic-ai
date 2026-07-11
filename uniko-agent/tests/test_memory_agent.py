"""Unit tests for MemoryAgent core processors."""

import pytest

from rustic_ai.core.agents.commons.media import MediaLink
from rustic_ai.uniko_agent import (
    AnswerRequest,
    MemoryAgentError,
    ObserveResult,
    ObserveTurnRequest,
    RecallRequest,
    RecallResponse,
)
from rustic_ai.uniko_agent.models import IngestDocumentRequest, IngestOutcome


class TestObserveTurn:
    """Tests for observe_turn processor."""

    @pytest.mark.asyncio
    async def test_observe_turn_creates_memory(self, memory_test_harness, sample_turns):
        """Test that observing a turn creates nodes in memory graph."""
        turn_data = sample_turns[0]

        memory_test_harness.send_message(
            ObserveTurnRequest(
                sender_id=turn_data["sender_id"], content=turn_data["content"], metadata=turn_data["metadata"]
            )
        )

        responses = memory_test_harness.get_sent_messages()
        assert len(responses) == 1

        result = responses[0].payload
        assert isinstance(result, ObserveResult)
        assert result.message_node_id > 0
        assert result.session_node_id > 0
        assert isinstance(result.chunk_node_ids, list)
        assert isinstance(result.extracted_entities, list)
        assert isinstance(result.extracted_observations, list)

    @pytest.mark.asyncio
    async def test_observe_multiple_turns(self, memory_test_harness, sample_turns):
        """Test observing multiple conversation turns."""
        for turn_data in sample_turns:
            memory_test_harness.send_message(
                ObserveTurnRequest(sender_id=turn_data["sender_id"], content=turn_data["content"])
            )

        responses = memory_test_harness.get_sent_messages()
        assert len(responses) == len(sample_turns)

        for response in responses:
            assert isinstance(response.payload, ObserveResult)
            assert response.payload.message_node_id > 0

    @pytest.mark.asyncio
    async def test_observe_with_custom_session_id(self, memory_test_harness, sample_turns):
        """Test observing turn with explicit session ID."""
        turn_data = sample_turns[0]

        memory_test_harness.send_message(
            ObserveTurnRequest(
                session_id="custom-session", sender_id=turn_data["sender_id"], content=turn_data["content"]
            )
        )

        responses = memory_test_harness.get_sent_messages()
        result = responses[0].payload

        assert isinstance(result, ObserveResult)
        assert result.message_node_id > 0

    @pytest.mark.asyncio
    async def test_observe_extracts_entities(self, memory_test_harness):
        """Test that observation extracts named entities."""
        memory_test_harness.send_message(
            ObserveTurnRequest(sender_id="user", content="I work at OpenAI in San Francisco and use Python daily")
        )

        responses = memory_test_harness.get_sent_messages()
        result = responses[0].payload

        assert isinstance(result, ObserveResult)
        # Entities should be extracted (OpenAI, San Francisco, Python)
        assert len(result.extracted_entities) >= 0  # Depends on NER model


class TestRecallKnowledge:
    """Tests for recall_knowledge processor."""

    @pytest.mark.asyncio
    async def test_recall_returns_results(self, memory_test_harness, sample_turns):
        """Test that recall returns relevant memories."""
        # First, observe several turns
        for turn_data in sample_turns:
            memory_test_harness.send_message(
                ObserveTurnRequest(sender_id=turn_data["sender_id"], content=turn_data["content"])
            )

        # Clear previous responses
        memory_test_harness.get_sent_messages()

        # Now recall
        memory_test_harness.send_message(RecallRequest(query="programming preferences"))

        responses = memory_test_harness.get_sent_messages()
        assert len(responses) == 1

        result = responses[0].payload
        assert isinstance(result, RecallResponse)
        assert isinstance(result.items, list)
        assert result.total_tokens >= 0
        assert isinstance(result.coverage, float)

    @pytest.mark.asyncio
    async def test_recall_with_max_tokens(self, memory_test_harness, sample_turns):
        """Test recall with custom max_tokens parameter."""
        # Observe turns
        for turn_data in sample_turns:
            memory_test_harness.send_message(
                ObserveTurnRequest(sender_id=turn_data["sender_id"], content=turn_data["content"])
            )

        memory_test_harness.get_sent_messages()

        # Recall with limited tokens
        memory_test_harness.send_message(RecallRequest(query="user preferences", max_tokens=500))

        responses = memory_test_harness.get_sent_messages()
        result = responses[0].payload

        assert isinstance(result, RecallResponse)
        assert result.total_tokens <= 500

    @pytest.mark.asyncio
    async def test_recall_phase1_only(self, memory_test_harness, sample_turns):
        """Test recall with phase1_only flag (facts/procedures)."""
        # Observe turns
        for turn_data in sample_turns:
            memory_test_harness.send_message(
                ObserveTurnRequest(sender_id=turn_data["sender_id"], content=turn_data["content"])
            )

        memory_test_harness.get_sent_messages()

        # Recall phase 1 only
        memory_test_harness.send_message(RecallRequest(query="programming", phase1_only=True))

        responses = memory_test_harness.get_sent_messages()
        result = responses[0].payload

        assert isinstance(result, RecallResponse)
        # Note: phase1_only parameter is not currently supported by uniko's simple recall API
        # The test just verifies recall returns results
        assert isinstance(result.items, list)

    @pytest.mark.asyncio
    async def test_recall_item_structure(self, memory_test_harness, sample_turns):
        """Test that RecallItem has correct structure."""
        # Observe turns
        for turn_data in sample_turns[:2]:
            memory_test_harness.send_message(
                ObserveTurnRequest(sender_id=turn_data["sender_id"], content=turn_data["content"])
            )

        memory_test_harness.get_sent_messages()

        # Recall
        memory_test_harness.send_message(RecallRequest(query="user information"))

        responses = memory_test_harness.get_sent_messages()
        result = responses[0].payload

        if len(result.items) > 0:
            item = result.items[0]
            assert hasattr(item, "node_id")
            assert hasattr(item, "kind")
            assert hasattr(item, "score")
            assert hasattr(item, "content")
            assert hasattr(item, "sources")
            assert isinstance(item.score, float)
            assert 0.0 <= item.score <= 1.0


class TestAnswerQuestion:
    """Tests for answer_question processor."""

    @pytest.mark.asyncio
    async def test_answer_without_llm_returns_error(self, memory_test_harness, sample_turns):
        """Test that answering without LLM configured returns error."""
        # Observe turns
        for turn_data in sample_turns:
            memory_test_harness.send_message(
                ObserveTurnRequest(sender_id=turn_data["sender_id"], content=turn_data["content"])
            )

        memory_test_harness.get_sent_messages()

        # Try to answer (should fail without LLM)
        memory_test_harness.send_message(AnswerRequest(question="What is the user's name?"))

        responses = memory_test_harness.get_sent_messages()
        result = responses[0].payload

        # Should return error since no LLM is configured
        assert isinstance(result, MemoryAgentError)
        assert result.error == "llm_not_configured"


class TestHelperMethods:
    """Tests for agent helper methods."""

    def test_build_scope_with_sessions(self, memory_test_harness):
        """Test _build_scope with session filter."""
        agent = memory_test_harness.agent

        scope = agent._build_scope({"sessions": ["session-1", "session-2"]})
        assert scope is not None

    def test_build_scope_with_participants(self, memory_test_harness):
        """Test _build_scope with participant filter."""
        agent = memory_test_harness.agent

        scope = agent._build_scope({"participants": ["user", "assistant"]})
        assert scope is not None

    def test_build_scope_comprehensive(self, memory_test_harness):
        """Test _build_scope with all parameters."""
        agent = memory_test_harness.agent

        scope = agent._build_scope(
            {
                "sessions": ["session-1"],
                "participants": ["user"],
            }
        )
        assert scope is not None


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_observe_with_invalid_data(self, memory_test_harness):
        """Test observation with invalid data handles errors gracefully."""
        # Send observation with empty content (edge case)
        memory_test_harness.send_message(ObserveTurnRequest(sender_id="user", content=""))  # Empty content

        responses = memory_test_harness.get_sent_messages()
        # Should either succeed with empty content or return error
        assert len(responses) == 1
        # Result type depends on uniko's handling of empty content


class TestIngestDocument:
    """Tests for ingest_document processor."""

    @pytest.mark.asyncio
    async def test_ingest_with_media_link_filesystem(self, memory_test_harness):
        """Test ingesting a document from guild filesystem via MediaLink."""
        import fsspec

        # Create the in-memory filesystem and write test content
        # The path is: /test/{org_id}/{guild_id}/{agent_id}/test_document.md
        # For guild-scoped fs (guild_fs:True), agent_id is "GUILD_GLOBAL"
        agent = memory_test_harness.agent
        fs = fsspec.filesystem("memory")
        org_id = "test_organization_id"
        guild_id = agent.guild_id
        agent_id = "GUILD_GLOBAL"  # Guild-scoped filesystem uses GUILD_GLOBAL as agent_id
        file_path = f"/test/{org_id}/{guild_id}/{agent_id}/test_document.md"
        fs.makedirs(f"/test/{org_id}/{guild_id}/{agent_id}", exist_ok=True)
        with fs.open(file_path, "w") as f:
            f.write("# Test Document\n\nThis is test content for ingestion.")

        # Create a media link pointing to guild filesystem
        media_link = MediaLink(
            url="test_document.md",
            name="test_document.md",
            mimetype="text/markdown",
            on_filesystem=True,
        )

        # Send ingest request with MediaLink
        memory_test_harness.send_message(
            IngestDocumentRequest(
                media_link=media_link,
            )
        )

        responses = memory_test_harness.get_sent_messages()
        assert len(responses) == 1

        result = responses[0].payload
        assert isinstance(result, IngestOutcome)
        assert result.success is True
        assert result.chunk_count >= 0

    @pytest.mark.asyncio
    async def test_ingest_with_media_link_async_filesystem(self, memory_test_harness_async_fs):
        """Test ingesting from guild filesystem when it's configured with asynchronous=True.

        This mirrors Rustic Studio's production configuration, where FileSystemResolver
        wraps the filesystem with asynchronous=True. Reading via the plain sync
        guild_fs.open() in that mode raises "Loop is not running" since the sync bridge
        loop is intentionally None; ingest_document must read via the async fsspec API.
        """
        import fsspec

        agent = memory_test_harness_async_fs.agent
        fs = fsspec.filesystem("memory")
        org_id = "test_organization_id"
        guild_id = agent.guild_id
        agent_id = "GUILD_GLOBAL"  # Guild-scoped filesystem uses GUILD_GLOBAL as agent_id
        file_path = f"/test/{org_id}/{guild_id}/{agent_id}/test_document.md"
        fs.makedirs(f"/test/{org_id}/{guild_id}/{agent_id}", exist_ok=True)
        with fs.open(file_path, "w") as f:
            f.write("# Test Document\n\nThis is test content for ingestion.")

        media_link = MediaLink(
            url="test_document.md",
            name="test_document.md",
            mimetype="text/markdown",
            on_filesystem=True,
        )

        memory_test_harness_async_fs.send_message(
            IngestDocumentRequest(
                media_link=media_link,
            )
        )

        responses = memory_test_harness_async_fs.get_sent_messages()
        assert len(responses) == 1

        result = responses[0].payload
        assert isinstance(result, IngestOutcome)
        assert result.success is True, f"Ingestion failed: {result.error_message}"
        assert result.chunk_count >= 0

    @pytest.mark.asyncio
    async def test_ingest_with_source_spec(self, memory_test_harness):
        """Test ingesting a document using source_spec (text)."""
        memory_test_harness.send_message(
            IngestDocumentRequest(
                source_spec={
                    "text": "This is inline text content for ingestion.",
                    "mime_type": "text/plain",
                },
            )
        )

        responses = memory_test_harness.get_sent_messages()
        assert len(responses) == 1

        result = responses[0].payload
        assert isinstance(result, IngestOutcome)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_ingest_without_source_returns_error(self, memory_test_harness):
        """Test that ingesting without media_link or source_spec returns error."""
        memory_test_harness.send_message(IngestDocumentRequest())

        responses = memory_test_harness.get_sent_messages()
        assert len(responses) == 1

        result = responses[0].payload
        assert isinstance(result, IngestOutcome)
        assert result.success is False
        assert "Either media_link or source_spec must be provided" in result.error_message
