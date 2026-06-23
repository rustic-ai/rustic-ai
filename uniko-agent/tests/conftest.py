"""Test fixtures for MemoryAgent tests."""

import pytest
import pytest_asyncio
import uniko
from rustic_ai.core.guild.builders import AgentBuilder, GuildBuilder
from rustic_ai.core.guild.dsl import DependencySpec, GuildSpec
from rustic_ai.testing.helpers import wrap_agent_for_testing
from rustic_ai.uniko_agent import MemoryAgent, MemoryAgentConfig, UnikoResolver


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
            "streaming": False,
        }
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


@pytest.fixture
def memory_test_harness(memory_agent_spec, uniko_dependency_spec):
    """Provides test harness for MemoryAgent.

    Args:
        memory_agent_spec: Agent specification fixture
        uniko_dependency_spec: Uniko dependency specification

    Returns:
        Tuple of (agent, messages list)
    """
    agent, messages = wrap_agent_for_testing(
        agent_spec=memory_agent_spec,
        dependency_map={"uniko": uniko_dependency_spec},
    )

    # Create a simple harness-like object
    class TestHarness:
        def __init__(self, agent, messages):
            self.agent = agent
            self.messages = messages

        def send_message(self, payload):
            """Send a message to the agent."""
            from rustic_ai.core.messaging.core.message import Message
            from rustic_ai.core.utils.gemstone_id import GemstoneGenerator
            from rustic_ai.core.utils.qualified_name import get_qualified_class_name

            id_gen = GemstoneGenerator(machine_id=1, datacenter_id=1)
            msg = Message(
                id=id_gen.generate(),
                source_agent_id="test",
                target_agent_id=self.agent.id,
                format=get_qualified_class_name(payload.__class__),
                payload=payload.model_dump(mode="json"),
            )
            self.agent._process_message(msg)

        def get_sent_messages(self):
            """Get messages sent by the agent."""
            result = list(self.messages)
            self.messages.clear()
            return result

    return TestHarness(agent, messages)


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
            "metadata": {"topic": "programming"}
        },
        {
            "sender_id": "user",
            "content": "My name is Nihal",
            "metadata": {"topic": "personal"}
        },
        {
            "sender_id": "assistant",
            "content": "Nice to meet you, Nihal! Python is a great choice for development.",
            "metadata": {"topic": "greeting"}
        },
    ]
