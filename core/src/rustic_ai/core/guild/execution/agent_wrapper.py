from abc import ABC, abstractmethod
import logging
from typing import Any, Dict, Optional, Type

from rustic_ai.core.guild.agent import Agent, AgentSpec
from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
)
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.guild.execution.utils import (
    build_agent_from_spec,
    subscribe_agent_with_messaging,
)
from rustic_ai.core.messaging import (
    Client,
    MessageTrackingClient,
    MessagingConfig,
    MessagingInterface,
)
from rustic_ai.core.utils.class_utils import get_agent_class


class AgentWrapper(ABC):
    """
    Abstract base class for agent wrappers that handles common initialization logic for agents and their connection to the Messaging Interface.
    """

    def __init__(
        self,
        guild_spec: GuildSpec,
        agent_spec: AgentSpec,
        messaging_config: MessagingConfig,
        machine_id: int,
        client_type: Type[Client] = MessageTrackingClient,
        client_properties: Dict[str, Any] = {},
    ):
        """
        Initializes a new instance of the AgentWrapper class.

        Args:
            guild_spec: The spec for the guild this agent is being launched in.
            agent_spec: The agent specification or instance to wrap.
                NOTE: Providing an Agent is only supported for testing and should not be used in production.
            messaging_config: The messaging configuration to use for the agent.
            machine_id: A unique identifier for the machine generating the ID.
            client_type: The type of client to use for the agent.
            client_properties: Properties to initialize the client with.
            dependencies: A dictionary of dependencies for the agent.
        """
        # Create a named logger for this class
        self.logger = logging.getLogger(f"{guild_spec.id}.{guild_spec.name}.{agent_spec.name}")

        self.agent: Optional[Agent] = None

        self.agent_spec = agent_spec

        self.guild_spec = guild_spec
        self.messaging_config = messaging_config
        self.machine_id = machine_id
        self.client_type = client_type
        self.client_properties = client_properties
        self.messaging: MessagingInterface
        self.messaging_owned = False
        self.dependencies = guild_spec.dependency_map | self.agent_spec.dependency_map
        self.only_agent_class_name = self.agent_spec.class_name.split(".")[-1]

    def initialize_agent(self) -> Agent:
        """
        Common logic for initializing the agent with the Messaging and its client.
        """
        self.logger.info(
            f"Starting initialization of agent {self.agent_spec.name} from class {self.agent_spec.class_name}"
        )

        agent_class = get_agent_class(self.agent_spec.class_name)

        # Initialize the agent's dependencies
        self.logger.debug(f"Loading dependencies for agent {self.agent_spec.name}")
        agent_deps = agent_class.list_all_dependencies()

        self.logger.debug(f"Agent dependencies: {agent_deps}")

        # Initialize the Messaging
        self.logger.info(f"Initializing messaging from config: {self.messaging_config}")
        self.messaging = MessagingInterface(self.guild_spec.id, self.messaging_config)
        self.logger.debug(f"Messaging initialized: {self.messaging}")
        self.messaging_owned = True

        self.agent = build_agent_from_spec(
            agent_spec=self.agent_spec,
            guild_spec=self.guild_spec,
            dependencies=self.dependencies,
            client_class=self.client_type,
            client_props=self.client_properties.copy(),
            machine_id=self.machine_id,
        )

        subscribe_agent_with_messaging(self.agent, self.messaging)

        # Notify the agent that it is ready to process messages
        self.logger.info(f"Agent {self.agent_spec.name} is ready to process messages")
        self.agent._notify_ready()

        return self.agent

    def _load_dependency_resolver(self, name: str) -> DependencyResolver:
        """
        Loads the dependency resolver for the given name.

        Args:
            name (str): The name of the dependency resolver.

        Returns:
            DependencyResolver: The dependency resolver for the agent.
        """
        if name in self.dependencies:
            resolver = self.dependencies[name].to_resolver()
            resolver.set_dependency_specs(self.dependencies)
            return resolver
        else:  # pragma: no cover
            raise ValueError(f"Dependency {name} not found in agent dependencies.")

    @abstractmethod
    def run(self) -> Optional[Agent]:
        """
        Runs the agent. This method should be implemented by concrete subclasses to define specific execution logic.
        """
        pass  # pragma: no cover

    def shutdown(self) -> None:
        """
        Shuts down the agent and its connection to the Messaging.
        """
        if self.agent is None:
            return

        # Check if messaging exists (could be a race condition in threaded environments)
        if hasattr(self, "messaging") and self.messaging is not None:
            for topic in self.agent.subscribed_topics:
                self.messaging.unsubscribe(topic, self.agent._get_client())

            self.messaging.unregister_client(self.agent._get_client())

            if self.messaging_owned:
                self.messaging.shutdown()
