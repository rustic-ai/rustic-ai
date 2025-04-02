import pytest

from rustic_ai.core.agents.testutils.probe_agent import ProbeAgent
from rustic_ai.core.guild.builders import AgentBuilder
from rustic_ai.core.guild.execution.sync.sync_exec_engine import SyncExecutionEngine
from rustic_ai.core.guild.guild import Guild
from rustic_ai.core.messaging.core.messaging_config import MessagingConfig
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator

TEST_GUILD_COUNT: int = 0


@pytest.fixture
def guild() -> Guild:
    global TEST_GUILD_COUNT
    TEST_GUILD_COUNT += 1
    guild_id = f"test_guild_{TEST_GUILD_COUNT}"

    messaging_config: MessagingConfig = MessagingConfig(
        backend_module="rustic_ai.core.messaging.backend",
        backend_class="InMemoryMessagingBackend",
        backend_config={},
    )

    # Create and return a Guild
    return Guild(
        id=guild_id,
        name="Test Guild",
        description="A test guild",
        execution_engine_clz=SyncExecutionEngine.get_qualified_class_name(),
        messaging_config=messaging_config,
    )


@pytest.fixture
def probe_agent():

    probe: ProbeAgent = (
        AgentBuilder(ProbeAgent).set_id("test_agent").set_name("Test Agent").set_description("A test agent").build()
    )

    yield probe

    probe.clear_messages()


@pytest.fixture
def generator() -> GemstoneGenerator:
    """
    Fixture that returns a GemstoneGenerator instance with a seed of 1.
    """
    return GemstoneGenerator(1)
