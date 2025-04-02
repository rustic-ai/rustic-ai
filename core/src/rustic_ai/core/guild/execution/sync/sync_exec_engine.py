from typing import Any, Dict, List, Type, Union

from rustic_ai.core.guild.agent import Agent, AgentSpec
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.guild.execution.execution_engine import ExecutionEngine
from rustic_ai.core.guild.execution.sync.agent_tracker import InMemorySyncAgentTracker
from rustic_ai.core.guild.execution.sync.sync_agent_wrapper import SyncAgentWrapper
from rustic_ai.core.messaging import Client, MessageTrackingClient, MessagingConfig


class SyncExecutionEngine(ExecutionEngine):
    def __init__(self, guild_id: str) -> None:
        super().__init__(guild_id=guild_id)
        self.agent_tracker = InMemorySyncAgentTracker()
        self.owned_agents: List[tuple[str, str]] = []

    """
    A synchronous execution engine that runs agents within the same thread and process.
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
        Instantiates a SynchronousAgentWrapper to handle the agent's initialization with the message bus, then runs the agent synchronously.

        Parameters:
            agent: The agent specification or instance to wrap.
                NOTE: Providing an Agent is only supported for testing and should not be used in production.
            messaging_config: Messaging configuration.
            client_type: The type of client to be used by the agent for communicating with the message bus.
            client_properties: Additional properties for initializing the client.
            default_topic: The default topic the agent should subscribe to.
        """
        # Instantiate the synchronous agent wrapper with the provided parameters
        guild_id = guild_spec.id

        agent_wrapper = SyncAgentWrapper(
            guild_spec=guild_spec,
            agent_spec=agent_spec,
            messaging_config=messaging_config,
            machine_id=machine_id,
            client_type=client_type,
            client_properties=client_properties,
        )

        # Add the agent to the tracker
        actual_spec = agent_spec if isinstance(agent_spec, AgentSpec) else agent_spec.get_spec()
        self.agent_tracker.add_agent(guild_id, actual_spec, agent_wrapper)

        self.owned_agents.append((guild_id, agent_spec.id))

        # Execute the agent using the wrapper
        agent_wrapper.run()

    def get_agents_in_guild(self, guild_id: str) -> Dict[str, AgentSpec]:
        """
        Returns the agents that are currently running in the guild.

        Parameters:
            guild_id: The ID of the guild

        Returns:
            Dict[str, AgentSpec]: A dictionary of agents that are currently running in the guild.
        """
        return self.agent_tracker.get_agents_in_guild(guild_id)

    def find_agents_by_name(self, guild_id: str, agent_name: str) -> List[AgentSpec]:
        """
        Returns the agents that are currently running in the guild with the specified name.

        Parameters:
            guild_id: The ID of the guild
            agent_name: The name of the agent

        Returns:
            Dict[str, AgentSpec]: A dictionary of agents that are currently running in the guild with the specified name.
        """
        return self.agent_tracker.find_agents_by_name(guild_id, agent_name)

    def is_agent_running(self, guild_id: str, agent_id: str) -> bool:
        """
        Checks if an agent is currently running.

        Parameters:
            guild_id: The ID of the guild
            agent_id: The ID of the agent

        Returns:
            bool: True if the agent is running, False otherwise.
        """
        return self.agent_tracker.get_agent_wrapper(guild_id, agent_id) is not None

    def stop_agent(self, guild_id: str, agent_id: str) -> None:
        """
        Stops an agent that is currently running.

        Parameters:
            guild_id: The ID of the guild
            agent_id: The ID of the agent
        """
        agent_wrapper = self.agent_tracker.get_agent_wrapper(guild_id, agent_id)
        if agent_wrapper:
            agent_wrapper.shutdown()
            self.agent_tracker.remove_agent(guild_id, agent_id)
            del agent_wrapper
            # Remove the agent from the owned agents list
            self.owned_agents.remove((guild_id, agent_id))

    def shutdown(self) -> None:
        for guild_id, agent_id in self.owned_agents:
            self.stop_agent(guild_id, agent_id)

        self.agent_tracker.clear()
