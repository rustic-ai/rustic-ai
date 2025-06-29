import logging
import multiprocessing
from multiprocessing.synchronize import Event as EventType
import pickle
import time
from typing import Any, Dict, Optional, Type, Union

from rustic_ai.core.guild.agent import Agent, AgentSpec
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.messaging import Client, MessageTrackingClient, MessagingConfig

from ..agent_wrapper import AgentWrapper


def agent_process_function(
    guild_spec_data: bytes,
    agent_spec_data: bytes,
    messaging_config_data: bytes,
    machine_id: int,
    client_type_name: str,
    client_properties: Dict[str, Any],
    process_ready_event: EventType,
    shutdown_event: EventType,
):
    """
    Function that runs in the separate process to initialize and run the agent.

    Args:
        guild_spec_data: Pickled GuildSpec
        agent_spec_data: Pickled AgentSpec or Agent
        messaging_config_data: Pickled MessagingConfig
        machine_id: Machine identifier for ID generation
        client_type_name: Name of the client type to instantiate
        client_properties: Properties for client initialization
        process_ready_event: Event to signal when process is ready
        shutdown_event: Event to signal shutdown
    """
    try:
        # Deserialize the data
        guild_spec = pickle.loads(guild_spec_data)
        agent_spec = pickle.loads(agent_spec_data)
        messaging_config = pickle.loads(messaging_config_data)

        # Recreate the client type from its name defaulting to MessageTrackingClient
        from rustic_ai.core.messaging.client import MessageTrackingClient

        client_type = MessageTrackingClient

        # Initialize agent directly (similar to AgentWrapper.initialize_agent())
        from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import (
            DependencyResolver,
        )
        from rustic_ai.core.messaging import MessagingInterface
        from rustic_ai.core.utils.class_utils import create_agent_from_spec
        from rustic_ai.core.utils.gemstone_id import GemstoneGenerator

        logging.info(f"Starting initialization of agent {agent_spec.name} from class {agent_spec.class_name}")

        # Create agent instance
        if hasattr(agent_spec, "get_spec"):
            # It's an Agent instance
            agent = agent_spec
            agent_spec = agent.get_spec()
        else:
            # It's an AgentSpec
            agent = create_agent_from_spec(agent_spec)

        logging.info("Agent object instance created")

        # Set the guild_spec on the agent
        agent._set_guild_spec(guild_spec)

        # Initialize the agent's dependencies
        logging.info(f"Loading dependencies for agent {agent_spec.name}")
        agent_deps = agent.list_all_dependencies()
        logging.info(f"Agent dependencies: {agent_deps}")

        dependencies = guild_spec.dependency_map | agent_spec.dependency_map

        def load_dependency_resolver(name: str) -> DependencyResolver:
            if name in dependencies:
                resolver = dependencies[name].to_resolver()
                resolver.set_dependency_specs(dependencies)
                return resolver
            else:
                raise ValueError(f"Dependency {name} not found in agent dependencies.")

        dependency_resolvers = {dep.dependency_key: load_dependency_resolver(dep.dependency_key) for dep in agent_deps}
        agent._set_dependency_resolvers(dependency_resolvers)
        logging.info("Dependencies loaded")

        # Initialize the Messaging
        logging.info(f"Initializing messaging from config: {messaging_config}")
        messaging = MessagingInterface(agent.guild_id, messaging_config)
        logging.info(f"Messaging initialized: {messaging}")

        # Initialize client
        client_properties = client_properties.copy()
        client_properties.update({"id": agent.id, "name": agent.name, "message_handler": agent._on_message})

        client = client_type(**client_properties)
        agent._set_client(client)
        logging.info(f"Client initialized: {client}")

        generator = GemstoneGenerator(machine_id)
        agent._set_generator(generator)

        # Register the client with the Messaging and subscribe to the default topic
        messaging.register_client(client)
        for topic in agent.subscribed_topics:
            messaging.subscribe(topic, client)
            logging.info(f"Client registered and subscribed to topic: {topic}")

        # Signal that the process is ready
        process_ready_event.set()

        logging.info(f"Agent {agent.id} started in process {multiprocessing.current_process().pid}")

        # Keep the agent running until shutdown is signaled
        while not shutdown_event.is_set():
            time.sleep(0.1)

        logging.info(f"Agent {agent.id} shutting down in process {multiprocessing.current_process().pid}")

        # Clean shutdown
        for topic in agent.subscribed_topics:
            messaging.unsubscribe(topic, client)

        messaging.unregister_client(client)
        messaging.shutdown()

    except Exception as e:
        logging.error(f"Error in agent process: {e}", exc_info=True)
        process_ready_event.set()  # Signal ready even on error to prevent deadlock


class MultiProcessAgentWrapper(AgentWrapper):
    """
    An implementation of AgentWrapper that runs the agent in a separate process.
    This escapes the Python GIL and allows for true parallelism.
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
        super().__init__(
            guild_spec=guild_spec,
            agent_spec=agent_spec,
            messaging_config=messaging_config,
            machine_id=machine_id,
            client_type=client_type,
            client_properties=client_properties,
        )

        self.process: Optional[multiprocessing.Process] = None
        self.process_ready_event = multiprocessing.Event()
        self.shutdown_event = multiprocessing.Event()
        self.is_running = False

    def run(self) -> None:
        """
        Initializes the agent and runs it in a separate process.
        """
        try:
            # Serialize the data to pass to the process
            guild_spec_data = pickle.dumps(self.guild_spec)
            agent_spec_data = pickle.dumps(self.agent_spec)
            messaging_config_data = pickle.dumps(self.messaging_config)

            # Get the client type name for reconstruction in the process
            client_type_name = self.client_type.__name__

            # Create and start the process
            self.process = multiprocessing.Process(
                target=agent_process_function,
                args=(
                    guild_spec_data,
                    agent_spec_data,
                    messaging_config_data,
                    self.machine_id,
                    client_type_name,
                    self.client_properties,
                    self.process_ready_event,
                    self.shutdown_event,
                ),
                name=f"Agent-{self.agent_spec.id}",
            )

            self.process.start()
            self.is_running = True

            # Wait for the process to be ready (with timeout)
            if not self.process_ready_event.wait(timeout=30):
                logging.error(f"Agent {self.agent_spec.id} failed to start within timeout")
                self.shutdown()
                raise RuntimeError(f"Agent {self.agent_spec.id} failed to start")

            logging.info(f"Agent {self.agent_spec.id} started successfully in process {self.process.pid}")

        except Exception as e:
            logging.error(f"Failed to start agent {self.agent_spec.id}: {e}")
            self.shutdown()
            raise

    def shutdown(self) -> None:
        """
        Shuts down the agent process.
        """
        if not self.is_running:
            return

        self.is_running = False

        try:
            # Signal shutdown
            self.shutdown_event.set()

            if self.process and self.process.is_alive():
                # Give the process time to shutdown gracefully
                self.process.join(timeout=10)

                # Force terminate if still alive
                if self.process.is_alive():
                    logging.warning(f"Force terminating agent process {self.process.pid}")
                    self.process.terminate()
                    self.process.join(timeout=5)

                    # Last resort - kill
                    if self.process.is_alive():
                        logging.error(f"Force killing agent process {self.process.pid}")
                        self.process.kill()
                        self.process.join()

            logging.info(f"Agent {self.agent_spec.id} process terminated")

        except Exception as e:
            logging.error(f"Error shutting down agent {self.agent_spec.id}: {e}")

        finally:
            self.process = None

    def is_alive(self) -> bool:
        """
        Check if the agent process is still alive.

        Returns:
            bool: True if the process is alive, False otherwise
        """
        return self.process is not None and self.process.is_alive()

    def get_process_id(self) -> Optional[int]:
        """
        Get the process ID of the agent process.

        Returns:
            int: Process ID, or None if not running
        """
        return self.process.pid if self.process else None
