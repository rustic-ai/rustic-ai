from abc import ABC, abstractmethod
from typing import Any, Dict, List, Type, Union

from rustic_ai.core.guild.agent import Agent, AgentSpec
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.messaging import Client, MessageTrackingClient, MessagingConfig
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name


class ExecutionEngine(ABC):
    """
    Defines the interface for execution engines capable of running agents
    with flexible Messaging initialization.
    """

    def __init__(self, guild_id: str) -> None:
        self.guild_id = guild_id

    @abstractmethod
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
        Runs an agent by handling its initialization with the message bus.

        Parameters:
            agent: The agent to run.
            messaging: Either an instance of MessagingInterface or a configuration to initialize one
            machine_id: A unique identifier for the machine generating the ID
            client_type: The type of client to use for the agent.
            client_properties: Properties to initialize the client with.
            default_topic: The default topic to subscribe to.
        """
        pass  # pragma: no cover

    @abstractmethod
    def get_agents_in_guild(self, guild_id: str) -> Dict[str, AgentSpec]:
        """
        Returns the agents that are currently running in the guild.

        Parameters:
            guild_id: The ID of the guild

        Returns:
            Dict[str, AgentSpec]: A dictionary of agents that are currently running in the guild.
        """
        pass  # pragma: no cover

    @abstractmethod
    def find_agents_by_name(self, guild_id: str, agent_name: str) -> List[AgentSpec]:
        """
        Returns the agents that are currently running in the guild with the specified name.

        Parameters:
            guild_id: The ID of the guild
            agent_name: The name of the agent

        Returns:

            List[AgentSpec]: A list of agents that are currently running in the guild with the specified name.
        """
        pass  # pragma: no cover

    @abstractmethod
    def is_agent_running(self, guild_id: str, agent_id: str) -> bool:
        """
        Checks if an agent is currently running.

        Parameters:
            guild_id: The ID of the guild
            agent_id: The ID of the agent

        Returns:
            bool: True if the agent is running, False otherwise.
        """
        pass  # pragma: no cover

    @abstractmethod
    def stop_agent(self, guild_id: str, agent_id: str) -> None:
        """
        Stops an agent that is currently running.

        Parameters:
            guild_id: The ID of the guild
            agent_id: The ID of the agent
        """
        pass  # pragma: no cover

    @abstractmethod
    def shutdown(self) -> None:
        """
        Shutdown the execution engine.
        """
        pass  # pragma: no cover

    @classmethod
    def get_qualified_class_name(cls) -> str:
        """
        Returns the qualified name of the execution engine.

        Returns:
            str: The qualified name of the execution engine.
        """
        return get_qualified_class_name(cls)
