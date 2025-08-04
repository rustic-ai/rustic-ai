import logging
import multiprocessing
from multiprocessing.synchronize import Event as EventType
import time
from typing import Any, Dict, Optional, Type

from rustic_ai.core.guild.agent import AgentSpec
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.messaging import Client, MessageTrackingClient, MessagingConfig

from ..agent_wrapper import AgentWrapper


class MultiProcessAgentWrapper(AgentWrapper):
    """
    An implementation of AgentWrapper that runs the agent in a separate process.
    This escapes the Python GIL and allows for true parallelism.

    This implementation follows the proper pattern like sync and Ray implementations:
    - The execution engine handles process creation
    - The wrapper runs in the remote process and calls initialize_agent()
    - The wrapper focuses on agent initialization, not process management
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
        super().__init__(
            guild_spec=guild_spec,
            agent_spec=agent_spec,
            messaging_config=messaging_config,
            machine_id=machine_id,
            client_type=client_type,
            client_properties=client_properties,
        )

        # These are only used for tracking purposes in the main process
        self.process: Optional[multiprocessing.Process] = None
        self.shutdown_event: Optional[EventType] = None
        self.is_running = False

    def run(self) -> None:
        """
        Runs the agent. This follows the same pattern as sync and Ray implementations.

        The execution engine is responsible for process creation and calling this method
        in the remote process. This method just focuses on agent initialization.
        """
        try:
            # Perform common initialization tasks - this is the key method!
            # This is the same pattern as sync and Ray implementations
            logging.info(f"Initializing agent {self.agent_spec.name} in multiprocess wrapper")
            self.initialize_agent()
            logging.info(f"Agent {self.agent_spec.name} initialized successfully")

            # Keep the agent running until shutdown is signaled
            # This is similar to how Ray agents stay alive
            while self.shutdown_event is None or not self.shutdown_event.is_set():
                time.sleep(0.1)

            agent_id = self.agent.id if hasattr(self, "agent") and self.agent else "unknown"
            logging.info(f"Agent {agent_id} shutting down in process {multiprocessing.current_process().pid}")

            # Clean shutdown
            self._cleanup_agent()

        except Exception as e:
            logging.error(f"Error running agent {self.agent_spec.name} in multiprocess wrapper: {e}", exc_info=True)
            raise

    def _cleanup_agent(self) -> None:
        """
        Clean up the agent resources.
        """
        try:
            if hasattr(self, "agent") and self.agent:
                # Unsubscribe from topics
                if hasattr(self.agent, "subscribed_topics") and hasattr(self.agent, "client"):
                    for topic in self.agent.subscribed_topics:
                        if hasattr(self, "messaging") and self.messaging:
                            self.messaging.unsubscribe(topic, self.agent.client)  # type: ignore

                # Unregister client
                if hasattr(self, "messaging") and self.messaging and hasattr(self.agent, "client"):
                    self.messaging.unregister_client(self.agent.client)  # type: ignore

                # Shutdown messaging
                if hasattr(self, "messaging") and self.messaging:
                    self.messaging.shutdown()

        except Exception as e:
            logging.error(f"Error during agent cleanup: {e}")

    def shutdown(self) -> None:
        """
        Shuts down the agent process.
        This is only used for tracking purposes in the main process.
        """
        if not self.is_running:
            return

        self.is_running = False

        try:
            # Signal shutdown
            if self.shutdown_event:
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
            self.shutdown_event = None

    def is_alive(self) -> bool:
        """
        Check if the agent process is still alive.
        This is only used for tracking purposes in the main process.

        Returns:
            bool: True if the process is alive, False otherwise
        """
        return self.process is not None and self.process.is_alive()

    def get_process_id(self) -> Optional[int]:
        """
        Get the process ID of the agent process.
        This is only used for tracking purposes in the main process.

        Returns:
            int: Process ID, or None if not running
        """
        return self.process.pid if self.process else None
