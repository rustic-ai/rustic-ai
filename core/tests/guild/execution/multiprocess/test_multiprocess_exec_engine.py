import multiprocessing
from unittest.mock import Mock, patch

import pytest

from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.guild.execution.multiprocess.agent_tracker import (
    MultiProcessAgentTracker,
)
from rustic_ai.core.guild.execution.multiprocess.multiprocess_agent_wrapper import (
    MultiProcessAgentWrapper,
)
from rustic_ai.core.guild.execution.multiprocess.multiprocess_exec_engine import (
    MultiProcessExecutionEngine,
)
from rustic_ai.core.messaging.core.messaging_config import MessagingConfig

from rustic_ai.testing.execution.integration_agents import InitiatorProbeAgent


class TestMultiProcessExecutionEngine:
    """Unit tests for MultiProcessExecutionEngine."""

    @pytest.fixture
    def guild_id(self):
        return "test_guild"

    @pytest.fixture
    def engine(self, guild_id):
        # Use a small max_processes for testing
        engine = MultiProcessExecutionEngine(guild_id=guild_id, max_processes=2)
        yield engine
        engine.shutdown()

    @pytest.fixture
    def guild_spec(self, guild_id):
        return GuildSpec(id=guild_id, name="Test Guild", description="Test guild for multiprocess engine tests")

    @pytest.fixture
    def agent_spec(self):
        from rustic_ai.core.guild.builders import AgentBuilder

        return (
            AgentBuilder(InitiatorProbeAgent)
            .set_id("test_agent")
            .set_name("Test Agent")
            .set_description("Test agent for multiprocess tests")
            .build_spec()
        )

    @pytest.fixture
    def messaging_config(self):
        # Use in-memory backend for unit tests
        return MessagingConfig(
            backend_module="rustic_ai.core.messaging.backend.inmemory_backend",
            backend_class="InMemoryMessagingBackend",
            backend_config={},
        )

    def test_engine_initialization(self, guild_id):
        """Test that the engine initializes correctly."""
        engine = MultiProcessExecutionEngine(guild_id=guild_id, max_processes=4)

        assert engine.guild_id == guild_id
        assert engine.max_processes == 4
        assert isinstance(engine.agent_tracker, MultiProcessAgentTracker)
        assert len(engine.owned_agents) == 0

        engine.shutdown()

    def test_engine_initialization_default_max_processes(self, guild_id):
        """Test that the engine uses CPU count as default max_processes."""
        engine = MultiProcessExecutionEngine(guild_id=guild_id)

        assert engine.max_processes == multiprocessing.cpu_count()

        engine.shutdown()

    def test_get_agents_in_guild_empty(self, engine, guild_id):
        """Test getting agents from an empty guild."""
        agents = engine.get_agents_in_guild(guild_id)
        assert agents == {}

    def test_is_agent_running_nonexistent(self, engine, guild_id):
        """Test checking if a nonexistent agent is running."""
        assert not engine.is_agent_running(guild_id, "nonexistent_agent")

    def test_find_agents_by_name_empty(self, engine, guild_id):
        """Test finding agents by name in an empty guild."""
        agents = engine.find_agents_by_name(guild_id, "Test Agent")
        assert agents == []

    def test_get_engine_stats_empty(self, engine):
        """Test getting engine statistics when empty."""
        stats = engine.get_engine_stats()

        assert stats["engine_type"] == "MultiProcessExecutionEngine"
        assert stats["guild_id"] == engine.guild_id
        assert stats["max_processes"] == engine.max_processes
        assert stats["alive_agents"] == 0
        assert stats["total_agents"] == 0
        assert stats["owned_agents_count"] == 0

    def test_cleanup_dead_processes_empty(self, engine):
        """Test cleanup when there are no processes."""
        # Should not raise an exception
        engine.cleanup_dead_processes()

    def test_stop_nonexistent_agent(self, engine, guild_id):
        """Test stopping a nonexistent agent."""
        # Should not raise an exception
        engine.stop_agent(guild_id, "nonexistent_agent")

    def test_get_process_info_nonexistent(self, engine, guild_id):
        """Test getting process info for nonexistent agent."""
        info = engine.get_process_info(guild_id, "nonexistent_agent")
        assert info == {}

    @patch("rustic_ai.core.guild.execution.multiprocess.multiprocess_exec_engine.MultiProcessAgentWrapper")
    def test_run_agent_success(self, mock_wrapper_class, engine, guild_spec, agent_spec, messaging_config):
        """Test successfully running an agent."""
        # Setup mock
        mock_wrapper = Mock(spec=MultiProcessAgentWrapper)
        mock_wrapper.get_process_id.return_value = 12345
        mock_wrapper_class.return_value = mock_wrapper

        # Mock the agent tracker
        engine.agent_tracker = Mock(spec=MultiProcessAgentTracker)
        engine.agent_tracker.get_agents_in_guild.return_value = {}

        # Run agent
        engine.run_agent(guild_spec=guild_spec, agent_spec=agent_spec, messaging_config=messaging_config, machine_id=1)

        # Verify wrapper was created and run
        mock_wrapper_class.assert_called_once()
        mock_wrapper.run.assert_called_once()

        # Verify tracking
        engine.agent_tracker.add_agent.assert_called_once_with(guild_spec.id, agent_spec, mock_wrapper)
        assert (guild_spec.id, agent_spec.id) in engine.owned_agents

    @patch("rustic_ai.core.guild.execution.multiprocess.multiprocess_exec_engine.MultiProcessAgentWrapper")
    def test_run_agent_max_processes_exceeded(
        self, mock_wrapper_class, engine, guild_spec, agent_spec, messaging_config
    ):
        """Test that running an agent fails when max processes is exceeded."""
        # Mock the agent tracker to return max processes worth of agents
        engine.agent_tracker = Mock(spec=MultiProcessAgentTracker)
        mock_agents = {f"agent_{i}": Mock() for i in range(engine.max_processes)}
        engine.agent_tracker.get_agents_in_guild.return_value = mock_agents

        # Should raise RuntimeError
        with pytest.raises(RuntimeError, match="Maximum number of processes"):
            engine.run_agent(
                guild_spec=guild_spec, agent_spec=agent_spec, messaging_config=messaging_config, machine_id=1
            )

        # Wrapper should not be created
        mock_wrapper_class.assert_not_called()

    @patch("rustic_ai.core.guild.execution.multiprocess.multiprocess_exec_engine.MultiProcessAgentWrapper")
    def test_run_agent_wrapper_failure(self, mock_wrapper_class, engine, guild_spec, agent_spec, messaging_config):
        """Test handling of wrapper creation failure."""
        # Setup mock to raise exception
        mock_wrapper_class.side_effect = Exception("Wrapper creation failed")

        # Mock the agent tracker
        engine.agent_tracker = Mock(spec=MultiProcessAgentTracker)
        engine.agent_tracker.get_agents_in_guild.return_value = {}

        # Should raise the exception
        with pytest.raises(Exception, match="Wrapper creation failed"):
            engine.run_agent(
                guild_spec=guild_spec, agent_spec=agent_spec, messaging_config=messaging_config, machine_id=1
            )

        # Should clean up on failure
        engine.agent_tracker.remove_agent.assert_called_once_with(guild_spec.id, agent_spec.id)

    def test_stop_agent_success(self, engine, guild_id):
        """Test successfully stopping an agent."""
        agent_id = "test_agent"

        # Mock the agent tracker and wrapper
        mock_wrapper = Mock(spec=MultiProcessAgentWrapper)
        engine.agent_tracker = Mock(spec=MultiProcessAgentTracker)
        engine.agent_tracker.get_agent_wrapper.return_value = mock_wrapper
        engine.owned_agents.append((guild_id, agent_id))

        # Stop agent
        engine.stop_agent(guild_id, agent_id)

        # Verify shutdown was called
        mock_wrapper.shutdown.assert_called_once()
        engine.agent_tracker.remove_agent.assert_called_once_with(guild_id, agent_id)
        assert (guild_id, agent_id) not in engine.owned_agents

    def test_stop_agent_wrapper_not_found(self, engine, guild_id):
        """Test stopping an agent when wrapper is not found."""
        agent_id = "test_agent"

        # Mock the agent tracker to return None
        engine.agent_tracker = Mock(spec=MultiProcessAgentTracker)
        engine.agent_tracker.get_agent_wrapper.return_value = None

        # Should not raise exception
        engine.stop_agent(guild_id, agent_id)

    def test_shutdown_with_agents(self, engine, guild_id):
        """Test shutdown when there are running agents."""
        # Add some mock agents
        agent_ids = ["agent1", "agent2"]
        for agent_id in agent_ids:
            engine.owned_agents.append((guild_id, agent_id))

        # Mock the agent tracker
        mock_wrapper = Mock(spec=MultiProcessAgentWrapper)
        engine.agent_tracker = Mock(spec=MultiProcessAgentTracker)
        engine.agent_tracker.get_agent_wrapper.return_value = mock_wrapper

        # Shutdown
        engine.shutdown()

        # Verify all agents were stopped
        assert engine.agent_tracker.remove_agent.call_count == len(agent_ids)
        assert len(engine.owned_agents) == 0
        engine.agent_tracker.clear.assert_called_once()

    def test_cleanup_dead_processes_with_dead_agent(self, engine, guild_id):
        """Test cleanup of dead processes."""
        agent_id = "test_agent"
        engine.owned_agents.append((guild_id, agent_id))

        # Mock the agent tracker to return False for is_agent_alive
        engine.agent_tracker = Mock(spec=MultiProcessAgentTracker)
        engine.agent_tracker.is_agent_alive.return_value = False

        # Cleanup
        engine.cleanup_dead_processes()

        # Verify dead agent was removed
        engine.agent_tracker.remove_agent.assert_called_once_with(guild_id, agent_id)
        assert (guild_id, agent_id) not in engine.owned_agents

    def test_cleanup_dead_processes_with_alive_agent(self, engine, guild_id):
        """Test cleanup when all processes are alive."""
        agent_id = "test_agent"
        engine.owned_agents.append((guild_id, agent_id))

        # Mock the agent tracker to return True for is_agent_alive
        engine.agent_tracker = Mock(spec=MultiProcessAgentTracker)
        engine.agent_tracker.is_agent_alive.return_value = True

        # Cleanup
        engine.cleanup_dead_processes()

        # Verify no agents were removed
        engine.agent_tracker.remove_agent.assert_not_called()
        assert (guild_id, agent_id) in engine.owned_agents

    def test_get_process_info_success(self, engine, guild_id):
        """Test getting process info successfully."""
        agent_id = "test_agent"
        expected_info = {"pid": 12345, "status": "running"}

        # Mock the agent tracker
        engine.agent_tracker = Mock(spec=MultiProcessAgentTracker)
        engine.agent_tracker.get_process_info.return_value = expected_info

        # Get process info
        info = engine.get_process_info(guild_id, agent_id)

        assert info == expected_info
        engine.agent_tracker.get_process_info.assert_called_once_with(guild_id, agent_id)

    def test_delegated_methods(self, engine, guild_id):
        """Test that methods properly delegate to the agent tracker."""
        # Mock the agent tracker
        mock_agents = {"agent1": Mock()}
        mock_agent_list = [Mock()]

        engine.agent_tracker = Mock(spec=MultiProcessAgentTracker)
        engine.agent_tracker.get_agents_in_guild.return_value = mock_agents
        engine.agent_tracker.find_agents_by_name.return_value = mock_agent_list
        engine.agent_tracker.is_agent_alive.return_value = True

        # Test delegation
        result = engine.get_agents_in_guild(guild_id)
        assert result == mock_agents

        result = engine.find_agents_by_name(guild_id, "Test Agent")
        assert result == mock_agent_list

        result = engine.is_agent_running(guild_id, "test_agent")
        assert result is True

        # Verify calls were made
        engine.agent_tracker.get_agents_in_guild.assert_called_with(guild_id)
        engine.agent_tracker.find_agents_by_name.assert_called_with(guild_id, "Test Agent")
        engine.agent_tracker.is_agent_alive.assert_called_with(guild_id, "test_agent")


class TestMultiProcessAgentTracker:
    """Unit tests for MultiProcessAgentTracker."""

    @pytest.fixture
    def tracker(self):
        tracker = MultiProcessAgentTracker()
        yield tracker
        tracker.clear()

    @pytest.fixture
    def agent_spec(self):
        from rustic_ai.core.guild.builders import AgentBuilder

        return (
            AgentBuilder(InitiatorProbeAgent)
            .set_id("test_agent")
            .set_name("Test Agent")
            .set_description("Test agent for tracker tests")
            .build_spec()
        )

    def test_tracker_initialization(self, tracker):
        """Test that tracker initializes correctly."""
        assert len(tracker.shared_agents) == 0
        assert len(tracker.shared_agents_by_name) == 0
        assert len(tracker.local_wrappers) == 0

    def test_get_agent_spec_nonexistent(self, tracker):
        """Test getting spec for nonexistent agent."""
        spec = tracker.get_agent_spec("test_guild", "nonexistent")
        assert spec is None

    def test_get_agent_wrapper_nonexistent(self, tracker):
        """Test getting wrapper for nonexistent agent."""
        wrapper = tracker.get_agent_wrapper("test_guild", "nonexistent")
        assert wrapper is None

    def test_get_agents_in_guild_empty(self, tracker):
        """Test getting agents from empty guild."""
        agents = tracker.get_agents_in_guild("test_guild")
        assert agents == {}

    def test_find_agents_by_name_empty(self, tracker):
        """Test finding agents by name in empty guild."""
        agents = tracker.find_agents_by_name("test_guild", "Test Agent")
        assert agents == []

    def test_is_agent_alive_nonexistent(self, tracker):
        """Test checking if nonexistent agent is alive."""
        assert not tracker.is_agent_alive("test_guild", "nonexistent")

    def test_get_process_info_nonexistent(self, tracker):
        """Test getting process info for nonexistent agent."""
        info = tracker.get_process_info("test_guild", "nonexistent")
        assert info is None

    def test_get_stats_empty(self, tracker):
        """Test getting stats when tracker is empty."""
        stats = tracker.get_stats()

        assert stats["total_agents"] == 0
        assert stats["alive_agents"] == 0
        assert stats["total_guilds"] == 0
        assert stats["local_wrappers"] == 0

    @patch("rustic_ai.core.guild.execution.multiprocess.agent_tracker.pickle")
    def test_add_agent_success(self, mock_pickle, tracker, agent_spec):
        """Test successfully adding an agent."""
        # Mock pickle
        mock_pickle.dumps.return_value = b"serialized_spec"

        # Mock wrapper
        mock_wrapper = Mock(spec=MultiProcessAgentWrapper)
        mock_wrapper.get_process_id.return_value = 12345
        mock_wrapper.is_alive.return_value = True

        # Add agent
        tracker.add_agent("test_guild", agent_spec, mock_wrapper)

        # Verify tracking
        assert "test_guild" in tracker.shared_agents
        assert agent_spec.id in tracker.shared_agents["test_guild"]
        assert "test_guild" in tracker.shared_agents_by_name
        assert agent_spec.name in tracker.shared_agents_by_name["test_guild"]

        wrapper_key = f"test_guild:{agent_spec.id}"
        assert wrapper_key in tracker.local_wrappers
        assert tracker.local_wrappers[wrapper_key] == mock_wrapper

    def test_remove_agent_success(self, tracker):
        """Test successfully removing an agent."""
        # Add some mock data first
        guild_id = "test_guild"
        agent_id = "test_agent"

        # Properly initialize shared data structures
        tracker.shared_agents[guild_id] = tracker.manager.dict()
        tracker.shared_agents[guild_id][agent_id] = (b"spec_data", {"pid": 123})

        tracker.shared_agents_by_name[guild_id] = tracker.manager.dict()
        tracker.shared_agents_by_name[guild_id]["Test Agent"] = tracker.manager.list()
        tracker.shared_agents_by_name[guild_id]["Test Agent"].append(agent_id)

        wrapper_key = f"{guild_id}:{agent_id}"
        tracker.local_wrappers[wrapper_key] = Mock()

        # Remove agent
        tracker.remove_agent(guild_id, agent_id)

        # Verify removal - check if guild dict is empty or agent is removed
        if guild_id in tracker.shared_agents:
            assert agent_id not in tracker.shared_agents[guild_id]

        # Check name tracking
        if guild_id in tracker.shared_agents_by_name and "Test Agent" in tracker.shared_agents_by_name[guild_id]:
            assert len(tracker.shared_agents_by_name[guild_id]["Test Agent"]) == 0

        # Check local wrapper removal
        assert wrapper_key not in tracker.local_wrappers

    def test_clear_success(self, tracker):
        """Test clearing the tracker."""
        # Add some mock data
        mock_wrapper = Mock(spec=MultiProcessAgentWrapper)
        tracker.local_wrappers["test:agent"] = mock_wrapper
        tracker.shared_agents["test"] = tracker.manager.dict()
        tracker.shared_agents_by_name["test"] = tracker.manager.dict()

        # Clear
        tracker.clear()

        # Verify cleanup
        mock_wrapper.shutdown.assert_called_once()
        assert len(tracker.local_wrappers) == 0
        assert len(tracker.shared_agents) == 0
        assert len(tracker.shared_agents_by_name) == 0
