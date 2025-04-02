import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type, Union

from rustic_ai.core.guild.agent import Agent, AgentSpec
from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
    DependencyResolver,
)
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.messaging import (
    Client,
    MessageTrackingClient,
    MessagingConfig,
    MessagingInterface,
)
from rustic_ai.core.utils.class_utils import create_agent_from_spec
from rustic_ai.core.utils.gemstone_id import GemstoneGenerator


class AgentWrapper(ABC):
    """
    Abstract base class for agent wrappers that handles common initialization logic for agents and their connection to the Messaging Interface.
    """

    def __init__(
        self,
        guild_spec: GuildSpec,
        agent_spec: Union[AgentSpec, Agent],
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
        self.agent: Optional[Agent] = None

        if isinstance(agent_spec, Agent):
            self.agent = agent_spec
            self.agent_spec = agent_spec.get_spec()
        else:
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

    def initialize_agent(self) -> None:
        """
        Common logic for initializing the agent with the Messaging and its client.
        """
        logging.info(f"Starting initialization of agent {self.agent_spec.name} from class {self.agent_spec.class_name}")
        if self.agent is None:
            self.agent = create_agent_from_spec(self.agent_spec)

        logging.info("Agent object instance created")
        # Set the guild_spec on the agent
        self.agent._set_guild_spec(self.guild_spec)

        # Initialize the agent's dependencies
        logging.info(f"Loading dependencies for agent {self.agent_spec.name}")
        agent_deps = self.agent.list_all_dependencies()

        logging.info(f"Agent dependencies: {agent_deps}")

        dependecy_resolvers = {
            dep.dependency_key: self._load_dependency_resolver(dep.dependency_key) for dep in agent_deps
        }
        self.agent._set_dependency_resolvers(dependecy_resolvers)
        logging.info("Dependencies loaded")

        # Initialize the Messaging
        logging.info(f"Initializing messaging from config: {self.messaging_config}")
        self.messaging = MessagingInterface(self.agent.guild_id, self.messaging_config)
        logging.info(f"Messaging initialized: {self.messaging}")
        self.messaging_owned = True

        client_properties = self.client_properties.copy()

        # Logic to initialize the client based on client_class and client_properties
        client_properties.update(
            {"id": self.agent.id, "name": self.agent.name, "message_handler": self.agent._on_message}
        )

        client = self.client_type(**client_properties)
        self.agent._set_client(client)
        logging.info(f"Client initialized: {client}")

        generator = GemstoneGenerator(self.machine_id)
        self.agent._set_generator(generator)

        # Register the client with the Messaging and subscribe to the default topic
        self.messaging.register_client(client)
        for topic in self.agent.subscribed_topics:
            self.messaging.subscribe(topic, client)
            logging.info(f"Client registered and subscribed to topic: {topic}")

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
    def run(self) -> None:
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

        for topic in self.agent.subscribed_topics:
            self.messaging.unsubscribe(topic, self.agent._get_client())

        self.messaging.unregister_client(self.agent._get_client())

        if self.messaging_owned:
            self.messaging.shutdown()
