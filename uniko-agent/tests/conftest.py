"""Test fixtures for MemoryAgent tests."""

import pytest
import pytest_asyncio
import uniko

from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import DependencySpec
from rustic_ai.uniko_agent import MemoryAgent, MemoryAgentConfig, ObserveTurnRequest

from rustic_ai.testing.helpers import wrap_agent_for_testing


@pytest.fixture
def filesystem_dependency_spec():
    """Provides DependencySpec for in-memory filesystem.

    Returns:
        DependencySpec: Spec for FilesystemResolver with in-memory storage
    """
    return DependencySpec(
        class_name="rustic_ai.core.guild.agent_ext.depends.filesystem.FileSystemResolver",
        properties={
            "protocol": "memory",
            "path_base": "/test",
            "storage_options": {},
        },
    )


@pytest.fixture
def filesystem_dependency_spec_async():
    """Provides DependencySpec for in-memory filesystem configured with asynchronous=True.

    Mirrors the filesystem dependency configuration used by Rustic Studio in production,
    where FileSystemResolver wraps the filesystem with asynchronous=True.

    Returns:
        DependencySpec: Spec for FilesystemResolver with in-memory storage, async mode
    """
    return DependencySpec(
        class_name="rustic_ai.core.guild.agent_ext.depends.filesystem.FileSystemResolver",
        properties={
            "protocol": "memory",
            "path_base": "/test",
            "storage_options": {},
            "asynchronous": True,
        },
    )


@pytest_asyncio.fixture
async def in_memory_uniko():
    """Provides an in-memory uniko instance for testing.

    Yields:
        uniko.Agent: Test uniko agent handle

    Cleanup:
        Shuts down the uniko instance after test
    """
    uni = await uniko.Uniko.in_memory()
    agent = uni.agent("test-agent")
    yield agent
    await uni.shutdown()


@pytest.fixture
def memory_agent_config():
    """Provides default MemoryAgent configuration for tests.

    Returns:
        MemoryAgentConfig: Test configuration with auto_flush enabled
    """
    return MemoryAgentConfig(
        default_session_id="test-session",
        recall_max_tokens=2000,
        answer_max_tokens=500,
        auto_flush=True,
    )


@pytest.fixture
def uniko_dependency_spec():
    """Provides DependencySpec for in-memory uniko resolver.

    Returns:
        DependencySpec: Spec for UnikoResolver with in-memory storage
    """
    return DependencySpec(
        class_name="rustic_ai.uniko_agent.UnikoResolver",
        properties={
            "storage_path": None,  # In-memory
            "llm_spec": None,  # No LLM for basic tests
            "streaming": True,  # Enable streaming for auto_flush to work
        },
    )


@pytest.fixture
def memory_agent_spec(memory_agent_config, uniko_dependency_spec):
    """Provides MemoryAgent spec for tests.

    Args:
        memory_agent_config: Agent configuration fixture
        uniko_dependency_spec: Uniko dependency fixture

    Returns:
        AgentSpec: Configured MemoryAgent spec
    """
    return (
        AgentBuilder(MemoryAgent)
        .set_id("memory_agent")
        .set_name("Memory Agent")
        .set_description("Test memory agent")
        .set_properties(memory_agent_config)
        .set_dependency_map({"uniko": uniko_dependency_spec})
        .build_spec()
    )


@pytest.fixture
def minimal_guild_spec():
    """Provides minimal GuildSpec for testing.

    Returns:
        GuildSpec: Minimal guild configuration
    """
    return (
        GuildBuilder(guild_id="test-guild", guild_name="Test Guild", guild_description="Test")
        .set_execution_engine("rustic_ai.core.guild.execution.sync.sync_exec_engine.SyncExecutionEngine")
        .build_spec()
    )


class _MemoryTestHarness:
    """Simple harness-like object wrapping an agent under test."""

    def __init__(self, agent, messages):
        self.agent = agent
        self.messages = messages

    def send_message(self, payload):
        """Send a message to the agent."""
        from rustic_ai.core.messaging.core.message import AgentTag, Message
        from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
        from rustic_ai.core.utils.gemstone_id import GemstoneGenerator, Priority

        id_gen = GemstoneGenerator(1)
        id_obj = id_gen.get_id(Priority.NORMAL)
        msg = Message(
            id_obj=id_obj,
            sender=AgentTag(name="test", agent_id="test"),
            topics=["default"],
            format=get_qualified_class_name(payload.__class__),
            payload=payload.model_dump(mode="json"),
            recipient_list=[],
        )
        msg.topic_published_to = "default"
        self.agent._on_message(msg)

    def get_sent_messages(self, deserialize=True):
        """Get messages sent by the agent.

        Args:
            deserialize: If True, deserialize message payloads to Pydantic models

        Returns:
            List of messages with optionally deserialized payloads
        """
        from rustic_ai.core.utils.basic_class_utils import get_class_from_name

        result = list(self.messages)
        self.messages.clear()

        if deserialize:
            for msg in result:
                if msg.format and isinstance(msg.payload, dict):
                    try:
                        payload_class = get_class_from_name(msg.format)
                        msg.payload = payload_class(**msg.payload)
                    except Exception:
                        # If deserialization fails, keep the dict
                        pass

        return result


def _build_memory_test_harness(memory_agent_spec, uniko_dependency_spec, filesystem_dependency_spec):
    agent, messages = wrap_agent_for_testing(
        agent_spec=memory_agent_spec,
        dependency_map={
            "uniko": uniko_dependency_spec,
            "filesystem": filesystem_dependency_spec,
        },
    )

    harness = _MemoryTestHarness(agent, messages)

    # Initialize participant by observing an initial turn
    # This is required for goal/task management in uniko
    harness.send_message(
        ObserveTurnRequest(
            sender_id="memory_agent_test_guild", content="System initialized", metadata={"type": "system_init"}
        )
    )
    # Clear the initialization message
    harness.get_sent_messages()

    return harness


@pytest.fixture
def memory_test_harness(memory_agent_spec, uniko_dependency_spec, filesystem_dependency_spec):
    """Provides test harness for MemoryAgent.

    Args:
        memory_agent_spec: Agent specification fixture
        uniko_dependency_spec: Uniko dependency specification
        filesystem_dependency_spec: Filesystem dependency specification

    Returns:
        Tuple of (agent, messages list)
    """
    return _build_memory_test_harness(memory_agent_spec, uniko_dependency_spec, filesystem_dependency_spec)


@pytest.fixture
def memory_test_harness_async_fs(memory_agent_spec, uniko_dependency_spec, filesystem_dependency_spec_async):
    """Provides test harness for MemoryAgent with the filesystem dependency in async mode.

    Mirrors the Rustic Studio production configuration (filesystem.asynchronous=True),
    which requires guild_fs reads in ingest_document to go through the async fsspec API.

    Args:
        memory_agent_spec: Agent specification fixture
        uniko_dependency_spec: Uniko dependency specification
        filesystem_dependency_spec_async: Filesystem dependency specification, async mode

    Returns:
        Tuple of (agent, messages list)
    """
    return _build_memory_test_harness(memory_agent_spec, uniko_dependency_spec, filesystem_dependency_spec_async)


@pytest.fixture
def sample_turns():
    """Provides sample conversation turns for testing.

    Returns:
        list[dict]: List of turn specifications
    """
    return [
        {
            "sender_id": "user",
            "content": "I prefer working in Python over JavaScript",
            "metadata": {"topic": "programming"},
        },
        {"sender_id": "user", "content": "My name is Nihal", "metadata": {"topic": "personal"}},
        {
            "sender_id": "assistant",
            "content": "Nice to meet you, Nihal! Python is a great choice for development.",
            "metadata": {"topic": "greeting"},
        },
    ]
