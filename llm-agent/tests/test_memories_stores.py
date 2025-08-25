from collections import deque
from types import SimpleNamespace

from rustic_ai.core.guild.agent_ext.mixins.state_refresher import StateRefresherMixin
from rustic_ai.llm_agent.memories.history_memories_store import (
    HistoryBasedMemoriesStore,
)
from rustic_ai.llm_agent.memories.queue_memories_store import (
    QueueBasedMemoriesStore,
)
from rustic_ai.llm_agent.memories.state_memories_store import (
    StateBackedMemoriesStore,
)


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
