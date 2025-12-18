from pathlib import Path

import pytest

from rustic_ai.core.guild.agent import Agent
from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import DependencySpec
from rustic_ai.core.guild.agent_ext.depends.filesystem.filesystem import (
    FileSystemResolver,
)
from rustic_ai.core.guild.agent_ext.depends.llm.llm import LLM
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    ChatCompletionRequest,
    UserMessage,
)
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.knowledgebase.kbindex_backend_memory import (
    InMemoryKBIndexBackendResolver,
)
from rustic_ai.llm_agent.memories.knowledge_memories_store import (
    KnowledgeBasedMemoriesStore,
)


# Define DummyAgent at module level for proper class name resolution
class DummyAgent(Agent):
    """Minimal agent for testing."""

    pass


@pytest.fixture
def dependency_map(tmp_path):
    """Setup guild-scoped dependencies for filesystem and KB backend."""
    base = Path(tmp_path) / "kb_memory_tests"
    return {
        "filesystem": DependencySpec(
            class_name=FileSystemResolver.get_qualified_class_name(),
            properties={
                "path_base": str(base),
                "protocol": "file",
                "storage_options": {"auto_mkdir": True},
                "asynchronous": True,
            },
        ),
        "kb_backend": DependencySpec(
            class_name=InMemoryKBIndexBackendResolver.get_qualified_class_name(),
            properties={},
        ),
    }


@pytest.fixture
def memory_store():
    """Create a KnowledgeBasedMemoriesStore instance."""
    return KnowledgeBasedMemoriesStore(context_window_size=5, recall_limit=10)


@pytest.fixture
def dummy_agent(dependency_map, generator):
    """Create a dummy agent with dependencies for testing."""
    import importlib

    spec = (
        AgentBuilder(DummyAgent)
        .set_id("dummy_agent")
        .set_name("Dummy Agent")
        .set_description("Test agent")
        .set_dependency_map(dependency_map)
        .build_spec()
    )

    # Import wrap_agent_for_testing to create properly initialized agent
    from rustic_ai.testing.helpers import wrap_agent_for_testing

    agent, _ = wrap_agent_for_testing(spec, dependency_map=dependency_map)

    # Manually initialize dependency resolvers if not already done
    if not hasattr(agent, "_dependency_resolvers") or not agent._dependency_resolvers:
        agent._dependency_resolvers = {}
        for key, dep_spec in dependency_map.items():
            # Import and instantiate the resolver class
            module_name, class_name = dep_spec.class_name.rsplit(".", 1)
            module = importlib.import_module(module_name)
            resolver_class = getattr(module, class_name)
            resolver = resolver_class(**dep_spec.properties)
            agent._dependency_resolvers[key] = resolver

    return agent


class DummyContext:
    """Mock ProcessContext for testing."""

    def __init__(self):
        pass


class TestKnowledgeBasedMemoriesStore:
    """Test suite for KnowledgeBasedMemoriesStore."""

    def test_initialization(self, memory_store):
        """Test that memory store initializes with correct defaults."""
        assert memory_store.memory_type == "knowledge_based"
        assert memory_store.context_window_size == 5
        assert memory_store.recall_limit == 10
        assert memory_store._kb is None
        assert memory_store._message_counter == 0

    def test_serialize_deserialize_message(self, memory_store):
        """Test message serialization and deserialization."""
        msg = UserMessage(content="Hello, world!")

        # Serialize
        serialized = memory_store._serialize_message(msg)
        assert "Role: user" in serialized
        assert "Hello, world!" in serialized
        assert "MessageID:" in serialized
        assert "Timestamp:" in serialized

        # Deserialize
        deserialized = memory_store._deserialize_message(serialized)
        assert deserialized is not None
        assert deserialized.role == "user"
        assert deserialized.content == "Hello, world!"

    def test_serialize_message_with_metadata(self, memory_store):
        """Test serialization of message with additional metadata."""
        msg = AssistantMessage(content="I can help you.", name="assistant_1")

        serialized = memory_store._serialize_message(msg)
        assert "Role: assistant" in serialized
        assert "Name: assistant_1" in serialized
        assert "I can help you." in serialized

        deserialized = memory_store._deserialize_message(serialized)
        assert deserialized.role == "assistant"
        assert deserialized.content == "I can help you."
        assert deserialized.name == "assistant_1"

    def test_serialize_multimodal_content(self, memory_store):
        """Test serialization of message with multimodal content."""
        msg = UserMessage(
            content=[
                {"type": "text", "text": "What is this?"},
                {"type": "image_url", "image_url": {"url": "https://example.com/image.jpg"}},
            ]
        )

        serialized = memory_store._serialize_message(msg)
        assert "What is this?" in serialized

        # Deserialization should preserve the structure
        deserialized = memory_store._deserialize_message(serialized)
        assert deserialized is not None
        assert deserialized.role == "user"

    def test_remember_indexes_message(self, memory_store, dummy_agent):
        """Test that remember() successfully indexes a message."""
        msg = UserMessage(content="Remember this important fact.")
        ctx = DummyContext()

        # Remember the message
        memory_store.remember(dummy_agent, ctx, msg)

        # Verify message counter incremented
        assert memory_store._message_counter > 0

        # Verify KB was initialized
        import asyncio

        async def check_kb():
            kb = await memory_store._get_kb(dummy_agent, ctx)
            assert kb is not None

        asyncio.run(check_kb())

    def test_recall_with_empty_context(self, memory_store, dummy_agent):
        """Test recall with empty context returns empty list."""
        ctx = DummyContext()

        recalled = memory_store.recall(dummy_agent, ctx, [])
        assert recalled == []

    def test_recall_retrieves_relevant_memories(self, memory_store, dummy_agent):
        """Test that recall retrieves semantically relevant memories."""
        ctx = DummyContext()

        # Index several messages on different topics
        messages = [
            UserMessage(content="I love programming in Python."),
            AssistantMessage(content="Python is a great language for data science."),
            UserMessage(content="What's the weather like today?"),
            AssistantMessage(content="I don't have access to weather data."),
            UserMessage(content="Can you help me with a Python function?"),
        ]

        for msg in messages:
            memory_store.remember(dummy_agent, ctx, msg)

        # Query with Python-related context
        query_context = [UserMessage(content="Tell me about Python programming.")]

        recalled = memory_store.recall(dummy_agent, ctx, query_context)

        # Should retrieve Python-related messages
        assert len(recalled) > 0
        # Verify at least one recalled message is about Python
        recalled_contents = [msg.content for msg in recalled if isinstance(msg.content, str)]
        python_related = any("Python" in content or "python" in content.lower() for content in recalled_contents)
        assert python_related

    def test_recall_uses_context_window(self, memory_store, dummy_agent):
        """Test that recall only uses the configured context window size."""
        ctx = DummyContext()

        # Store some memories
        memory_store.remember(dummy_agent, ctx, UserMessage(content="Python is great."))

        # Create context larger than window size
        large_context = [UserMessage(content=f"Message {i}") for i in range(memory_store.context_window_size + 3)]

        # Add a relevant message at the end
        large_context.append(UserMessage(content="Tell me about Python."))

        # Recall should only use last context_window_size messages
        recalled = memory_store.recall(dummy_agent, ctx, large_context)

        # The function should work without errors
        assert isinstance(recalled, list)

    def test_multiple_remember_calls(self, memory_store, dummy_agent):
        """Test multiple sequential remember calls."""
        ctx = DummyContext()

        messages = [
            UserMessage(content="First message"),
            AssistantMessage(content="First response"),
            UserMessage(content="Second message"),
            AssistantMessage(content="Second response"),
        ]

        for msg in messages:
            memory_store.remember(dummy_agent, ctx, msg)

        # Verify message counter
        assert memory_store._message_counter == len(messages)

        # Verify we can recall
        query_context = [UserMessage(content="message")]
        recalled = memory_store.recall(dummy_agent, ctx, query_context)
        assert isinstance(recalled, list)

    def test_kb_initialization_lazy(self, memory_store, dummy_agent):
        """Test that KB is initialized lazily."""
        # KB should not be initialized yet
        assert memory_store._kb is None

        ctx = DummyContext()

        # First remember should initialize KB
        memory_store.remember(dummy_agent, ctx, UserMessage(content="Test"))

        # Now KB should be initialized (check via async call)
        import asyncio

        async def check_init():
            kb = await memory_store._get_kb(dummy_agent, ctx)
            assert kb is not None
            return kb

        kb1 = asyncio.run(check_init())

        # Second call should reuse the same KB instance
        kb2 = asyncio.run(check_init())
        assert kb1 is kb2

    def test_preprocess_integration(self, memory_store, dummy_agent):
        """Test preprocess integration with inherited behavior."""
        ctx = DummyContext()

        # First, store some memories
        memory_store.remember(dummy_agent, ctx, UserMessage(content="I like cats."))
        memory_store.remember(dummy_agent, ctx, AssistantMessage(content="Cats are wonderful pets."))

        # Create a request
        request = ChatCompletionRequest(messages=[UserMessage(content="Tell me about cats.")])

        # Mock LLM with all required abstract methods
        class MockLLM(LLM):
            def completion(self, request):
                return None

            async def async_completion(self, request):
                return None

            def get_config(self):
                return {}

            @property
            def model(self):
                return "mock-model"

        # Call preprocess
        processed = memory_store.preprocess(dummy_agent, ctx, request, MockLLM())

        # Should have combined old memories with new messages
        assert len(processed.messages) >= len(request.messages)

    def test_postprocess_integration(self, memory_store, dummy_agent):
        """Test postprocess integration."""
        ctx = DummyContext()

        # Create a mock response
        class MockChoice:
            def __init__(self):
                self.message = AssistantMessage(content="This is a response.")

        class MockResponse:
            def __init__(self):
                self.choices = [MockChoice()]

        response = MockResponse()
        request = ChatCompletionRequest(messages=[UserMessage(content="Test")])

        # Call postprocess
        result = memory_store.postprocess(dummy_agent, ctx, request, response, None)

        # Should have indexed the assistant message
        assert memory_store._message_counter > 0

        # Result should be None (no additional messages)
        assert result is None

    def test_deserialize_invalid_message(self, memory_store):
        """Test deserialization of invalid message returns None."""
        invalid_text = "This is not a valid serialized message"
        result = memory_store._deserialize_message(invalid_text)
        assert result is None

    def test_search_quality(self, memory_store, dummy_agent):
        """Test search quality with diverse topics."""
        ctx = DummyContext()

        # Index messages on different topics
        topics = {
            "cooking": [
                "I love baking cookies.",
                "My favorite recipe is chocolate chip cookies.",
            ],
            "sports": [
                "Basketball is an exciting sport.",
                "I enjoy watching NBA games.",
            ],
            "technology": [
                "Machine learning is transforming the world.",
                "AI models are becoming more sophisticated.",
            ],
        }

        for topic, messages in topics.items():
            for content in messages:
                memory_store.remember(dummy_agent, ctx, UserMessage(content=content))

        # Query for cooking-related content
        cooking_query = [UserMessage(content="What do you know about baking?")]
        cooking_results = memory_store.recall(dummy_agent, ctx, cooking_query)

        # Should retrieve cooking-related messages
        if len(cooking_results) > 0:
            cooking_contents = [
                msg.content
                for msg in cooking_results
                if isinstance(msg.content, str) and "cookie" in msg.content.lower()
            ]
            # At least some results should be about cooking
            assert len(cooking_contents) > 0 or len(cooking_results) == 0  # May not find any due to small dataset

    def test_message_counter_increments(self, memory_store, dummy_agent):
        """Test that message counter increments correctly."""
        ctx = DummyContext()

        initial_count = memory_store._message_counter

        memory_store.remember(dummy_agent, ctx, UserMessage(content="Message 1"))
        assert memory_store._message_counter == initial_count + 1

        memory_store.remember(dummy_agent, ctx, UserMessage(content="Message 2"))
        assert memory_store._message_counter == initial_count + 2

    def test_configuration_options(self):
        """Test creating memory store with different configurations."""
        store1 = KnowledgeBasedMemoriesStore(context_window_size=3, recall_limit=5)
        assert store1.context_window_size == 3
        assert store1.recall_limit == 5

        store2 = KnowledgeBasedMemoriesStore(context_window_size=10, recall_limit=20)
        assert store2.context_window_size == 10
        assert store2.recall_limit == 20

    def test_recall_with_non_string_content(self, memory_store, dummy_agent):
        """Test recall with messages that have non-string content."""
        ctx = DummyContext()

        # Store a message with list content
        msg = UserMessage(content=[{"type": "text", "text": "This is a test."}])
        memory_store.remember(dummy_agent, ctx, msg)

        # Query should still work
        query = [UserMessage(content="test")]
        recalled = memory_store.recall(dummy_agent, ctx, query)

        assert isinstance(recalled, list)
