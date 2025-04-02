from typing import Any, Dict, List, Type, Union

from rustic_ai.core.guild.agent import Agent, AgentSpec
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.guild.execution.execution_engine import ExecutionEngine
from rustic_ai.core.guild.execution.multithreaded.agent_tracker import (
    InMemoryMTAgentTracker,
)
from rustic_ai.core.guild.execution.multithreaded.multithreaded_agent_wrapper import (
    MultiThreadedAgentWrapper,
)
from rustic_ai.core.messaging.client import MessageTrackingClient
from rustic_ai.core.messaging.core import Client, MessagingConfig


class MultiThreadedEngine(ExecutionEngine):
    def __init__(self, guild_id) -> None:
        super().__init__(guild_id=guild_id)
        self.agent_wrappers: Dict[str, MultiThreadedAgentWrapper] = {}

        # We use the in-memory agent tracker as this is still running in the same process
        self.agent_tracker = InMemoryMTAgentTracker()

        self.owned_agents: List[tuple[str, str]] = []

    """
    An execution engine that runs agents in separate threads for concurrent execution.
    """

    def run_agent(
        self,
        guild_spec: GuildSpec,
        agent_spec: Union[AgentSpec, Agent],
        messaging_config: MessagingConfig,
        machine_id: int,
        client_type: Type[Client] = MessageTrackingClient,
        client_properties: Dict[str, Any] = {},
        default_topic: str = "default_topic",
    ) -> None:
        """
        Creates a MultiThreadedAgentWrapper for the agent and runs it in a separate thread.

        Parameters are similar to those described in the ExecutionEngine ABC.
        """
        guild_id = guild_spec.id
        agent_wrapper = MultiThreadedAgentWrapper(
            guild_spec=guild_spec,
            agent_spec=agent_spec,
            messaging_config=messaging_config,
            machine_id=machine_id,
            client_type=client_type,
            client_properties=client_properties,
        )

        self.agent_wrappers[agent_spec.id] = agent_wrapper
        self.owned_agents.append((guild_id, agent_spec.id))

        actual_spec = agent_spec if isinstance(agent_spec, AgentSpec) else agent_spec.get_spec()
        self.agent_tracker.add_agent(guild_id, actual_spec, agent_wrapper)

        # Execute the agent using the wrapper
        agent_wrapper.run()

    def get_agents_in_guild(self, guild_id: str) -> Dict[str, AgentSpec]:
        """
        Returns all agents in the guild with the given ID.
        """
        return self.agent_tracker.get_agents_in_guild(guild_id)

    def is_agent_running(self, guild_id: str, agent_id: str) -> bool:
        """
        Returns whether the agent with the given ID is running in the guild with the given ID.
        """
        return self.agent_tracker.get_agent_wrapper(guild_id, agent_id) is not None

    def find_agents_by_name(self, guild_id: str, agent_name: str) -> List[AgentSpec]:
        """
        Returns all agents in the guild with the given name.
        """
        return self.agent_tracker.find_agents_by_name(guild_id, agent_name)

    def stop_agent(self, guild_id: str, agent_id: str) -> None:
        """
        Stops the agent with the given ID in the guild with the given ID.
        """
        agent_wrapper = self.agent_tracker.get_agent_wrapper(guild_id, agent_id)
        if agent_wrapper is not None:
            agent_wrapper.shutdown()
            self.agent_tracker.remove_agent(guild_id, agent_id)
            del self.agent_wrappers[agent_id]
            del agent_wrapper
            self.owned_agents.remove((guild_id, agent_id))

    def shutdown(self) -> None:
        for guild_id, agent_id in self.owned_agents:
            self.stop_agent(guild_id, agent_id)

        self.agent_tracker.clear()
