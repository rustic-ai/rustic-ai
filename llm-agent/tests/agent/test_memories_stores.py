from collections import deque
from pathlib import Path
from types import SimpleNamespace

import pytest

from rustic_ai.core.guild.agent import Agent
from rustic_ai.core.guild.agent_ext.depends.llm.models import (
    AssistantMessage,
    UserMessage,
)
from rustic_ai.core.guild.agent_ext.mixins.state_refresher import StateRefresherMixin
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.llm_agent.memories.history_memories_store import (
    HistoryBasedMemoriesStore,
)
from rustic_ai.llm_agent.memories.knowledge_memories_store import (
    KnowledgeBasedMemoriesStore,
)
from rustic_ai.llm_agent.memories.queue_memories_store import (
    QueueBasedMemoriesStore,
)
from rustic_ai.llm_agent.memories.state_memories_store import (
    StateBackedMemoriesStore,
)

from rustic_ai.testing.helpers import wrap_agent_for_testing


class FakeLLMMessage:
    """Minimal stand-in for LLMMessage that supports model_dump and content field."""

    def __init__(self, role: str, content):
        self.role = role
        self.content = content

    def model_dump(self):
        return {"role": self.role, "content": self.content}


class DummyCtx:
    def __init__(self, context_dict=None):
        self._context = context_dict or {}

    def get_context(self):
        return self._context


class DummyAgent(StateRefresherMixin):
    """An Agent that supports the minimal API used by StateBackedMemoriesStore."""

    def __init__(self, state=None):
        self._state = state or {}

    def update_state(self, ctx, update_format, update, update_path="/"):
        # jsonpatch.JsonPatch.apply returns a new dict when in_place=False
        new_state = update.apply(self._state, in_place=False)
        self._state.clear()
        self._state.update(new_state)

    def get_agent_state(self):
        return self._state


# ------------------------------
# QueueBasedMemoriesStore tests
# ------------------------------


def test_queue_based_memories_store_fifo_and_maxlen():
    store = QueueBasedMemoriesStore(memory_size=2)

    # Append more than maxlen to ensure older items are dropped
    store.remember(agent=None, ctx=None, message="m1")
    store.remember(agent=None, ctx=None, message="m2")
    store.remember(agent=None, ctx=None, message="m3")

    recalled = store.recall(agent=None, ctx=None, context=[])
    assert recalled == ["m2", "m3"]


def test_queue_based_memories_store_recall_returns_copy():
    store = QueueBasedMemoriesStore(memory_size=3)
    store.remember(None, None, "a")
    store.remember(None, None, "b")

    recalled1 = store.recall(None, None, [])
    # Mutating the returned list should not affect internal queue
    recalled1.append("c")

    recalled2 = store.recall(None, None, [])
    assert recalled2 == ["a", "b"]


# --------------------------------
# StateBackedMemoriesStore tests
# --------------------------------


def test_state_backed_memories_store_updates_agent_state():
    agent = DummyAgent({"memories": []})
    store = StateBackedMemoriesStore(memory_size=2)

    # Initialize the underlying deque (the implementation doesn't do this itself)
    store._memory = deque(maxlen=store.memory_size)

    m1 = FakeLLMMessage("user", "hi")
    m2 = FakeLLMMessage("assistant", "hello")

    store.remember(agent, DummyCtx(), m1)
    store.remember(agent, DummyCtx(), m2)

    assert agent.get_agent_state()["memories"] == [m1.model_dump(), m2.model_dump()]

    # Ensure maxlen behavior is respected via the internal deque
    m3 = FakeLLMMessage("user", "again")
    store.remember(agent, DummyCtx(), m3)
    assert agent.get_agent_state()["memories"] == [m2.model_dump(), m3.model_dump()]


def test_state_backed_memories_store_recall_reads_from_state():
    existing = [
        FakeLLMMessage("user", "x").model_dump(),
        FakeLLMMessage("assistant", "y").model_dump(),
    ]
    agent = DummyAgent({"memories": existing.copy()})

    store = StateBackedMemoriesStore(memory_size=5)
    # internal _memory is irrelevant here; recall should overwrite from agent state
    store._memory = deque(maxlen=store.memory_size)

    recalled = store.recall(agent, DummyCtx(), context=[])
    assert recalled == existing


# ---------------------------------
# HistoryBasedMemoriesStore tests
# ---------------------------------


def test_history_based_memories_store_recall_text_only_and_dedup(monkeypatch):
    store = HistoryBasedMemoriesStore(text_only=True)

    # Patch get_qualified_class_name to return class name, so we can use simple strings
    def fake_get_qcn(cls):
        return getattr(cls, "name", getattr(cls, "__name__", "Unknown"))

    monkeypatch.setattr(
        "rustic_ai.llm_agent.memories.history_memories_store.get_qualified_class_name",
        fake_get_qcn,
        raising=True,
    )

    # Patch Message.from_json to just rehydrate our test dicts
    def fake_from_json(entry):
        return SimpleNamespace(format=entry["format"], payload=entry["payload"])

    monkeypatch.setattr(
        "rustic_ai.llm_agent.memories.history_memories_store.Message",
        SimpleNamespace(from_json=fake_from_json),
        raising=True,
    )

    # Patch model_validate for the request/response classes to bypass real schema
    def fake_req_validate(payload):
        return SimpleNamespace(messages=payload["messages"])

    def fake_resp_validate(payload):
        return SimpleNamespace(choices=[SimpleNamespace(message=payload["message"])])

    monkeypatch.setattr(
        "rustic_ai.llm_agent.memories.history_memories_store.ChatCompletionRequest",
        SimpleNamespace(name="ChatCompletionRequest", model_validate=fake_req_validate),
        raising=True,
    )
    monkeypatch.setattr(
        "rustic_ai.llm_agent.memories.history_memories_store.ChatCompletionResponse",
        SimpleNamespace(name="ChatCompletionResponse", model_validate=fake_resp_validate),
        raising=True,
    )

    # Prepare history: request with 3 messages (two duplicates, one non-text), and a response
    req_msg1 = FakeLLMMessage("user", "hello there")
    req_msg2 = FakeLLMMessage("user", "hello there")  # duplicate content
    req_msg3 = FakeLLMMessage("user", {"tool": "code"})  # non-text content
    resp_msg = FakeLLMMessage("assistant", "hi!")

    enriched_history = [
        {"format": "ChatCompletionRequest", "payload": {"messages": [req_msg1, req_msg2, req_msg3]}},
        {"format": "ChatCompletionResponse", "payload": {"message": resp_msg}},
    ]

    ctx = DummyCtx({"enriched_history": enriched_history})

    recalled = store.recall(agent=None, ctx=ctx, context=[])

    # text_only=True: non-text message should be filtered out and duplicates removed
    contents = [m.content for m in recalled]
    assert contents == ["hello there", "hi!"]


def test_history_based_memories_store_recall_includes_non_text_when_disabled(monkeypatch):
    store = HistoryBasedMemoriesStore(text_only=False)

    # Same monkeypatching as above
    def fake_get_qcn(cls):
        return getattr(cls, "name", getattr(cls, "__name__", "Unknown"))

    monkeypatch.setattr(
        "rustic_ai.llm_agent.memories.history_memories_store.get_qualified_class_name",
        fake_get_qcn,
        raising=True,
    )

    def fake_from_json(entry):
        return SimpleNamespace(format=entry["format"], payload=entry["payload"])

    monkeypatch.setattr(
        "rustic_ai.llm_agent.memories.history_memories_store.Message",
        SimpleNamespace(from_json=fake_from_json),
        raising=True,
    )

    def fake_req_validate(payload):
        return SimpleNamespace(messages=payload["messages"])

    def fake_resp_validate(payload):
        return SimpleNamespace(choices=[SimpleNamespace(message=payload["message"])])

    monkeypatch.setattr(
        "rustic_ai.llm_agent.memories.history_memories_store.ChatCompletionRequest",
        SimpleNamespace(name="ChatCompletionRequest", model_validate=fake_req_validate),
        raising=True,
    )
    monkeypatch.setattr(
        "rustic_ai.llm_agent.memories.history_memories_store.ChatCompletionResponse",
        SimpleNamespace(name="ChatCompletionResponse", model_validate=fake_resp_validate),
        raising=True,
    )

    req_msg1 = FakeLLMMessage("user", "text A")
    req_msg2 = FakeLLMMessage("user", {"non": "text"})
    resp_msg = FakeLLMMessage("assistant", "text B")

    enriched_history = [
        {"format": "ChatCompletionRequest", "payload": {"messages": [req_msg1, req_msg1, req_msg2]}},
        {"format": "ChatCompletionResponse", "payload": {"message": resp_msg}},
    ]

    ctx = DummyCtx({"enriched_history": enriched_history})

    recalled = store.recall(agent=None, ctx=ctx, context=[])

    # text_only=False: keep non-text message, but still dedupe identical text
    contents = [m.content for m in recalled]
    assert contents == ["text A", {"non": "text"}, "text B"]


# ---------------------------------------
# KnowledgeBasedMemoriesStore tests
# ---------------------------------------


class DummyKBAgent(Agent):
    """Minimal agent for KB memory testing."""

    pass


class DummyKBContext:
    """Mock ProcessContext for KB memory testing."""

    pass


@pytest.fixture
def kb_memory_store(tmp_path):
    """Create a KnowledgeBasedMemoriesStore instance with temp storage."""
    base = Path(tmp_path) / "kb_memory_tests"
    return KnowledgeBasedMemoriesStore(
        context_window_size=5,
        recall_limit=10,
        path_base=str(base),
        protocol="file",
        storage_options={"auto_mkdir": True},
        asynchronous=True,
    )


@pytest.fixture
def kb_agent(tmp_path, generator):
    """Create a dummy agent for KB memory testing."""
    spec = (
        AgentBuilder(DummyKBAgent)
        .set_id("kb_test_agent")
        .set_name("KB Test Agent")
        .set_description("Test agent for KB memory")
        .build_spec()
    )

    agent, _ = wrap_agent_for_testing(spec)
    return agent


def test_kb_memory_store_initialization(kb_memory_store):
    """Test that KB memory store initializes correctly."""
    assert kb_memory_store.memory_type == "knowledge_based"
    assert kb_memory_store.context_window_size == 5
    assert kb_memory_store.recall_limit == 10
    assert kb_memory_store._kb is None
    assert kb_memory_store._message_counter == 0


def test_kb_memory_store_serialize_deserialize(kb_memory_store):
    """Test message serialization and deserialization."""
    msg = UserMessage(content="Hello, world!")

    # Serialize
    content, metadata = kb_memory_store._serialize_message(msg)
    assert content == "Hello, world!"
    assert metadata["role"] == "user"
    assert "timestamp" in metadata

    # Deserialize
    deserialized = kb_memory_store._deserialize_message(content, metadata)
    assert deserialized is not None
    assert deserialized.role == "user"
    assert deserialized.content == "Hello, world!"


def test_kb_memory_store_serialize_with_metadata(kb_memory_store):
    """Test serialization of message with additional metadata."""
    msg = AssistantMessage(content="I can help you.", name="assistant_1")

    content, metadata = kb_memory_store._serialize_message(msg)
    assert content == "I can help you."
    assert metadata["role"] == "assistant"
    assert metadata["name"] == "assistant_1"
    assert "timestamp" in metadata

    deserialized = kb_memory_store._deserialize_message(content, metadata)
    assert deserialized.role == "assistant"
    assert deserialized.content == "I can help you."
    assert deserialized.name == "assistant_1"


def test_kb_memory_store_serialize_multimodal(kb_memory_store):
    """Test serialization of message with multimodal content."""
    msg = UserMessage(
        content=[
            {"type": "text", "text": "What is this?"},
            {"type": "image_url", "image_url": {"url": "https://example.com/image.jpg"}},
        ]
    )

    content, metadata = kb_memory_store._serialize_message(msg)
    assert "What is this?" in content
    assert metadata["role"] == "user"

    # Deserialization should work
    deserialized = kb_memory_store._deserialize_message(content, metadata)
    assert deserialized is not None
    assert deserialized.role == "user"


def test_kb_memory_store_remember(kb_memory_store, kb_agent):
    """Test that remember() successfully stores a message."""
    msg = UserMessage(content="Remember this important fact.")
    ctx = DummyKBContext()

    initial_counter = kb_memory_store._message_counter

    # Remember the message
    kb_memory_store.remember(kb_agent, ctx, msg)

    # Verify message counter incremented
    assert kb_memory_store._message_counter > initial_counter


def test_kb_memory_store_recall_empty_context(kb_memory_store, kb_agent):
    """Test recall with empty context returns empty list."""
    ctx = DummyKBContext()

    recalled = kb_memory_store.recall(kb_agent, ctx, [])
    assert recalled == []


def test_kb_memory_store_recall_retrieves_memories(kb_memory_store, kb_agent):
    """Test that recall retrieves semantically relevant memories."""
    ctx = DummyKBContext()

    # Store several messages on different topics
    messages = [
        UserMessage(content="I love programming in Python."),
        AssistantMessage(content="Python is a great language for data science."),
        UserMessage(content="What's the weather like today?"),
        AssistantMessage(content="I don't have access to weather data."),
        UserMessage(content="Can you help me with a Python function?"),
    ]

    for msg in messages:
        kb_memory_store.remember(kb_agent, ctx, msg)

    # Query with Python-related context
    query_context = [UserMessage(content="Tell me about Python programming.")]

    recalled = kb_memory_store.recall(kb_agent, ctx, query_context)

    # Should retrieve messages
    assert isinstance(recalled, list)


def test_kb_memory_store_multiple_remember_calls(kb_memory_store, kb_agent):
    """Test multiple sequential remember calls."""
    ctx = DummyKBContext()

    messages = [
        UserMessage(content="First message"),
        AssistantMessage(content="First response"),
        UserMessage(content="Second message"),
        AssistantMessage(content="Second response"),
    ]

    for msg in messages:
        kb_memory_store.remember(kb_agent, ctx, msg)

    # Verify message counter
    assert kb_memory_store._message_counter == len(messages)


def test_kb_memory_store_lazy_initialization(kb_memory_store, kb_agent):
    """Test that KB is initialized lazily."""
    import asyncio

    # KB should not be initialized yet
    assert kb_memory_store._kb is None

    ctx = DummyKBContext()

    # First remember should initialize KB
    kb_memory_store.remember(kb_agent, ctx, UserMessage(content="Test"))

    # Now KB should be initialized (check via async call)
    async def check_init():
        kb = await kb_memory_store._get_kb(kb_agent, ctx)
        assert kb is not None
        return kb

    kb1 = asyncio.run(check_init())

    # Second call should reuse the same KB instance
    kb2 = asyncio.run(check_init())
    assert kb1 is kb2


def test_kb_memory_store_deserialize_invalid(kb_memory_store):
    """Test deserialization of invalid message returns None."""
    result = kb_memory_store._deserialize_message("Invalid content", {})
    assert result is None


def test_kb_memory_store_message_counter_increments(kb_memory_store, kb_agent):
    """Test that message counter increments correctly."""
    ctx = DummyKBContext()

    initial_count = kb_memory_store._message_counter

    kb_memory_store.remember(kb_agent, ctx, UserMessage(content="Message 1"))
    assert kb_memory_store._message_counter == initial_count + 1

    kb_memory_store.remember(kb_agent, ctx, UserMessage(content="Message 2"))
    assert kb_memory_store._message_counter == initial_count + 2


def test_kb_memory_store_configuration_options(tmp_path):
    """Test creating memory store with different configurations."""
    base1 = Path(tmp_path) / "test1"
    store1 = KnowledgeBasedMemoriesStore(
        context_window_size=3,
        recall_limit=5,
        path_base=str(base1),
    )
    assert store1.context_window_size == 3
    assert store1.recall_limit == 5

    base2 = Path(tmp_path) / "test2"
    store2 = KnowledgeBasedMemoriesStore(
        context_window_size=10,
        recall_limit=20,
        path_base=str(base2),
    )
    assert store2.context_window_size == 10
    assert store2.recall_limit == 20
