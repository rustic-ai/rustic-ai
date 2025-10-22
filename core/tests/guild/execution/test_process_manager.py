"""Unit tests for AgentProcessManager."""

import pytest
import time
from typing import Optional

from rustic_ai.core.guild.agent import AgentSpec
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.guild.execution.process_manager import AgentProcessManager, AgentProcessInfo
from rustic_ai.core.messaging import MessagingConfig


@pytest.fixture
def process_manager():
    """Provide an AgentProcessManager instance."""
    manager = AgentProcessManager(max_processes=5)
    yield manager
    # Cleanup after each test
    manager.shutdown()


@pytest.fixture
def simple_agent_spec():
    """Provide a simple agent spec for testing."""
    return AgentSpec(
        id="test-agent-1",
        name="TestAgent1",
        class_name="rustic_ai.core.agent.Agent",  # Base Agent class
        description="Test agent",
        organization_id="test-org",
        guild_id="test-guild",
    )


@pytest.fixture
def simple_guild_spec():
    """Provide a simple guild spec for testing."""
    return GuildSpec(
        id="test-guild",
        name="TestGuild",
        description="Test guild",
        organization_id="test-org",
        agents=[],
    )


@pytest.fixture
def embedded_messaging_config():
    """Provide embedded messaging config for testing."""
    return MessagingConfig(backend_type="embedded", connection_params={})


class TestAgentProcessManagerBasics:
    """Test basic functionality of AgentProcessManager."""

    def test_initialization(self):
        """Test manager initialization."""
        manager = AgentProcessManager(max_processes=10)
        assert manager.max_processes == 10
        assert len(manager.processes) == 0
        manager.shutdown()

    def test_default_max_processes(self):
        """Test default max_processes value."""
        manager = AgentProcessManager()
        assert manager.max_processes == 100
        manager.shutdown()


class TestProcessSpawning:
    """Test process spawning functionality."""

    def test_spawn_single_process(self, process_manager, simple_agent_spec, simple_guild_spec, embedded_messaging_config):
        """Test spawning a single agent process."""
        agent_id = process_manager.spawn_agent_process(
            agent_spec=simple_agent_spec,
            guild_spec=simple_guild_spec,
            messaging_config=embedded_messaging_config,
            machine_id=0,
        )

        assert agent_id == "test-agent-1"
        assert agent_id in process_manager.processes
        assert process_manager.is_process_alive(agent_id)

    def test_spawn_multiple_processes(
        self, process_manager, simple_guild_spec, embedded_messaging_config
    ):
        """Test spawning multiple agent processes."""
        agent_ids = []

        for i in range(3):
            agent_spec = AgentSpec(
                id=f"test-agent-{i}",
                name=f"TestAgent{i}",
                class_name="rustic_ai.core.agent.Agent",
                description=f"Test agent {i}",
                organization_id="test-org",
                guild_id="test-guild",
            )

            agent_id = process_manager.spawn_agent_process(
                agent_spec=agent_spec,
                guild_spec=simple_guild_spec,
                messaging_config=embedded_messaging_config,
            )
            agent_ids.append(agent_id)

        assert len(agent_ids) == 3
        assert len(process_manager.processes) == 3

        # Verify all are alive
        for agent_id in agent_ids:
            assert process_manager.is_process_alive(agent_id)

    def test_spawn_exceeds_max_processes(
        self, simple_guild_spec, embedded_messaging_config
    ):
        """Test that spawning exceeds max_processes raises error."""
        manager = AgentProcessManager(max_processes=2)

        try:
            # Spawn 2 agents (should succeed)
            for i in range(2):
                agent_spec = AgentSpec(
                    id=f"test-agent-{i}",
                    name=f"TestAgent{i}",
                    class_name="rustic_ai.core.agent.Agent",
                    description=f"Test agent {i}",
                    organization_id="test-org",
                    guild_id="test-guild",
                )
                manager.spawn_agent_process(
                    agent_spec=agent_spec,
                    guild_spec=simple_guild_spec,
                    messaging_config=embedded_messaging_config,
                )

            # Third should fail
            agent_spec = AgentSpec(
                id="test-agent-3",
                name="TestAgent3",
                class_name="rustic_ai.core.agent.Agent",
                description="Test agent 3",
                organization_id="test-org",
                guild_id="test-guild",
            )

            with pytest.raises(RuntimeError, match="Maximum number of processes"):
                manager.spawn_agent_process(
                    agent_spec=agent_spec,
                    guild_spec=simple_guild_spec,
                    messaging_config=embedded_messaging_config,
                )

        finally:
            manager.shutdown()

    def test_spawn_duplicate_agent(
        self, process_manager, simple_agent_spec, simple_guild_spec, embedded_messaging_config
    ):
        """Test that spawning duplicate agent raises error."""
        # Spawn first time
        process_manager.spawn_agent_process(
            agent_spec=simple_agent_spec,
            guild_spec=simple_guild_spec,
            messaging_config=embedded_messaging_config,
        )

        # Spawn second time should fail
        with pytest.raises(RuntimeError, match="already exists"):
            process_manager.spawn_agent_process(
                agent_spec=simple_agent_spec,
                guild_spec=simple_guild_spec,
                messaging_config=embedded_messaging_config,
            )


class TestProcessStopping:
    """Test process stopping functionality."""

    def test_stop_running_process(
        self, process_manager, simple_agent_spec, simple_guild_spec, embedded_messaging_config
    ):
        """Test stopping a running process."""
        agent_id = process_manager.spawn_agent_process(
            agent_spec=simple_agent_spec,
            guild_spec=simple_guild_spec,
            messaging_config=embedded_messaging_config,
        )

        assert process_manager.is_process_alive(agent_id)

        # Stop the process
        success = process_manager.stop_agent_process(agent_id, timeout=5)
        assert success

        # Verify it's stopped
        assert not process_manager.is_process_alive(agent_id)
        assert agent_id not in process_manager.processes

    def test_stop_nonexistent_process(self, process_manager):
        """Test stopping a process that doesn't exist."""
        success = process_manager.stop_agent_process("nonexistent-agent")
        assert not success

    def test_stop_multiple_processes(
        self, process_manager, simple_guild_spec, embedded_messaging_config
    ):
        """Test stopping multiple processes."""
        agent_ids = []

        # Spawn 3 agents
        for i in range(3):
            agent_spec = AgentSpec(
                id=f"test-agent-{i}",
                name=f"TestAgent{i}",
                class_name="rustic_ai.core.agent.Agent",
                description=f"Test agent {i}",
                organization_id="test-org",
                guild_id="test-guild",
            )
            agent_id = process_manager.spawn_agent_process(
                agent_spec=agent_spec,
                guild_spec=simple_guild_spec,
                messaging_config=embedded_messaging_config,
            )
            agent_ids.append(agent_id)

        # Stop all
        for agent_id in agent_ids:
            success = process_manager.stop_agent_process(agent_id)
            assert success

        # Verify all stopped
        assert len(process_manager.processes) == 0


class TestProcessInfo:
    """Test process information retrieval."""

    def test_get_process_info(
        self, process_manager, simple_agent_spec, simple_guild_spec, embedded_messaging_config
    ):
        """Test getting process information."""
        agent_id = process_manager.spawn_agent_process(
            agent_spec=simple_agent_spec,
            guild_spec=simple_guild_spec,
            messaging_config=embedded_messaging_config,
        )

        info = process_manager.get_process_info(agent_id)

        assert info is not None
        assert info.agent_id == agent_id
        assert info.guild_id == "test-guild"
        assert info.agent_name == "TestAgent1"
        assert info.pid > 0
        assert info.is_alive
        assert info.created_at > 0

    def test_get_process_info_nonexistent(self, process_manager):
        """Test getting info for nonexistent process."""
        info = process_manager.get_process_info("nonexistent")
        assert info is None

    def test_list_all_processes(
        self, process_manager, simple_guild_spec, embedded_messaging_config
    ):
        """Test listing all processes."""
        # Spawn 2 agents
        for i in range(2):
            agent_spec = AgentSpec(
                id=f"test-agent-{i}",
                name=f"TestAgent{i}",
                class_name="rustic_ai.core.agent.Agent",
                description=f"Test agent {i}",
                organization_id="test-org",
                guild_id="test-guild",
            )
            process_manager.spawn_agent_process(
                agent_spec=agent_spec,
                guild_spec=simple_guild_spec,
                messaging_config=embedded_messaging_config,
            )

        processes = process_manager.list_processes()
        assert len(processes) == 2
        assert "test-agent-0" in processes
        assert "test-agent-1" in processes

    def test_list_processes_filtered_by_guild(
        self, process_manager, embedded_messaging_config
    ):
        """Test listing processes filtered by guild_id."""
        # Create two guilds
        guild1 = GuildSpec(
            id="guild-1", name="Guild1", description="Guild 1", organization_id="test-org", agents=[]
        )
        guild2 = GuildSpec(
            id="guild-2", name="Guild2", description="Guild 2", organization_id="test-org", agents=[]
        )

        # Spawn 2 agents in guild-1
        for i in range(2):
            agent_spec = AgentSpec(
                id=f"agent-guild1-{i}",
                name=f"Agent1_{i}",
                class_name="rustic_ai.core.agent.Agent",
                description=f"Agent in guild 1",
                organization_id="test-org",
                guild_id="guild-1",
            )
            process_manager.spawn_agent_process(
                agent_spec=agent_spec, guild_spec=guild1, messaging_config=embedded_messaging_config
            )

        # Spawn 1 agent in guild-2
        agent_spec = AgentSpec(
            id="agent-guild2-0",
            name="Agent2_0",
            class_name="rustic_ai.core.agent.Agent",
            description="Agent in guild 2",
            organization_id="test-org",
            guild_id="guild-2",
        )
        process_manager.spawn_agent_process(
            agent_spec=agent_spec, guild_spec=guild2, messaging_config=embedded_messaging_config
        )

        # List processes for guild-1
        guild1_processes = process_manager.list_processes(guild_id="guild-1")
        assert len(guild1_processes) == 2

        # List processes for guild-2
        guild2_processes = process_manager.list_processes(guild_id="guild-2")
        assert len(guild2_processes) == 1


class TestProcessCleanup:
    """Test dead process cleanup."""

    def test_cleanup_dead_processes(
        self, process_manager, simple_guild_spec, embedded_messaging_config
    ):
        """Test cleanup of dead processes."""
        # Spawn an agent
        agent_spec = AgentSpec(
            id="test-agent",
            name="TestAgent",
            class_name="rustic_ai.core.agent.Agent",
            description="Test agent",
            organization_id="test-org",
            guild_id="test-guild",
        )
        agent_id = process_manager.spawn_agent_process(
            agent_spec=agent_spec,
            guild_spec=simple_guild_spec,
            messaging_config=embedded_messaging_config,
        )

        # Stop it
        process_manager.stop_agent_process(agent_id)

        # Cleanup should not find any dead processes (already cleaned by stop)
        cleaned = process_manager.cleanup_dead_processes()
        assert len(cleaned) == 0


class TestShutdown:
    """Test manager shutdown."""

    def test_shutdown_with_running_processes(
        self, simple_guild_spec, embedded_messaging_config
    ):
        """Test shutdown with running processes."""
        manager = AgentProcessManager(max_processes=5)

        # Spawn 3 agents
        for i in range(3):
            agent_spec = AgentSpec(
                id=f"test-agent-{i}",
                name=f"TestAgent{i}",
                class_name="rustic_ai.core.agent.Agent",
                description=f"Test agent {i}",
                organization_id="test-org",
                guild_id="test-guild",
            )
            manager.spawn_agent_process(
                agent_spec=agent_spec,
                guild_spec=simple_guild_spec,
                messaging_config=embedded_messaging_config,
            )

        assert len(manager.processes) == 3

        # Shutdown should stop all
        manager.shutdown()

        assert len(manager.processes) == 0
        assert len(manager.process_info) == 0

    def test_shutdown_empty_manager(self):
        """Test shutdown with no running processes."""
        manager = AgentProcessManager()
        manager.shutdown()  # Should not raise
        assert len(manager.processes) == 0
