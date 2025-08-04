import logging
import multiprocessing
from multiprocessing.synchronize import Event as EventType
import pickle
from typing import Any, Dict, List, Optional, Type

from rustic_ai.core.guild.agent import Agent, AgentSpec
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.guild.execution.execution_engine import ExecutionEngine
from rustic_ai.core.messaging import Client, MessageTrackingClient, MessagingConfig

from .agent_tracker import MultiProcessAgentTracker
from .multiprocess_agent_wrapper import MultiProcessAgentWrapper


def multiprocess_wrapper_runner(
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
    Function that runs in the child process to execute the wrapper.
    This follows the proper pattern where the wrapper's run() method is called,
    which then calls initialize_agent() like sync and Ray implementations.
    """
    try:
        # Deserialize the data
        guild_spec = pickle.loads(guild_spec_data)
        agent_spec = pickle.loads(agent_spec_data)
        messaging_config = pickle.loads(messaging_config_data)

        # Reconstruct the client type
        from rustic_ai.core.messaging import MessageTrackingClient

        if client_type_name == "MessageTrackingClient":
            client_type = MessageTrackingClient
        else:
            # Default fallback
            client_type = MessageTrackingClient

        # Create the wrapper in the child process
        wrapper = MultiProcessAgentWrapper(
            guild_spec=guild_spec,
            agent_spec=agent_spec,
            messaging_config=messaging_config,
            machine_id=machine_id,
            client_type=client_type,
            client_properties=client_properties,
        )

        # Set the shutdown event for the wrapper
        wrapper.shutdown_event = shutdown_event

        # Signal that the process is ready before running the wrapper
        process_ready_event.set()

        # Run the wrapper - this will call initialize_agent() like sync/Ray
        wrapper.run()

    except Exception as e:
        logging.error(f"Error in multiprocess wrapper runner: {e}")
        raise


class MultiProcessExecutionEngine(ExecutionEngine):
    """
    An execution engine that runs agents in separate processes for true parallelism.
    This escapes the Python GIL and allows for genuine concurrent execution.

    This implementation follows the proper pattern where:
    1. The execution engine handles process creation
    2. The process runs the wrapper's run() method directly
    3. The wrapper calls initialize_agent() like sync/Ray implementations

    Features:
    - True parallelism by escaping the GIL
    - Process isolation for robustness
    - Shared memory tracking for agent management
    - Graceful shutdown handling
    """

    def __init__(self, guild_id: str, organization_id: str, max_processes: Optional[int] = None) -> None:
        """
        Initialize the multiprocess execution engine.

        Args:
            guild_id: The ID of the guild this engine manages
            organization_id: The organization ID
            max_processes: Maximum number of processes to allow (defaults to CPU count)
        """
        super().__init__(guild_id, organization_id)
        self.max_processes = max_processes or multiprocessing.cpu_count()
        self.agent_tracker = MultiProcessAgentTracker()
        self.owned_agents: List[tuple[str, str]] = []  # (guild_id, agent_id) pairs

        # Track running processes
        self.processes: Dict[str, multiprocessing.Process] = {}
        self.process_events: Dict[str, tuple[EventType, EventType]] = {}

        logging.info(f"MultiProcessExecutionEngine initialized with max_processes={self.max_processes}")

    def run_agent(
        self,
        guild_spec: GuildSpec,
        agent_spec: AgentSpec,
        messaging_config: MessagingConfig,
        machine_id: int,
        client_type: Type[Client] = MessageTrackingClient,
        client_properties: Dict[str, Any] = {},
        default_topic: str = "default_topic",
    ) -> Optional[Agent]:
        """
        Creates and runs an agent in a separate process.
        This follows the proper pattern where the execution engine handles process creation
        and the process runs the wrapper's run() method directly.

        Args:
            guild_spec: The guild specification
            agent_spec: The agent specification or instance to run
            messaging_config: Configuration for messaging
            machine_id: Unique machine identifier for ID generation
            client_type: Type of client to use for the agent
            client_properties: Properties to initialize the client with
            default_topic: Default topic for the agent (unused in this implementation)
        """
        try:
            guild_id = guild_spec.id

            # Ensure we have the agent spec
            actual_spec = agent_spec if isinstance(agent_spec, AgentSpec) else agent_spec.get_spec()

            # Check if we're at the process limit
            current_agents = self.agent_tracker.get_agents_in_guild(guild_id)
            if len(current_agents) >= self.max_processes:
                raise RuntimeError(f"Maximum number of processes ({self.max_processes}) reached")

            # Create events for process coordination
            process_ready_event = multiprocessing.Event()
            shutdown_event = multiprocessing.Event()

            # Serialize the data to pass to the process
            guild_spec_data = pickle.dumps(guild_spec)
            agent_spec_data = pickle.dumps(agent_spec)
            messaging_config_data = pickle.dumps(messaging_config)

            # Get the client type name for reconstruction in the process
            client_type_name = client_type.__name__

            # Create and start the process that will run the wrapper
            process = multiprocessing.Process(
                target=multiprocess_wrapper_runner,
                args=(
                    guild_spec_data,
                    agent_spec_data,
                    messaging_config_data,
                    machine_id,
                    client_type_name,
                    client_properties,
                    process_ready_event,
                    shutdown_event,
                ),
                name=f"Agent-{actual_spec.id}",
            )

            # Start the process
            process.start()

            # Wait for the process to be ready (with timeout)
            if not process_ready_event.wait(timeout=30):
                logging.error(f"Agent {actual_spec.id} failed to start within timeout")
                process.terminate()
                process.join(timeout=5)
                raise RuntimeError(f"Agent {actual_spec.id} failed to start")

            # Store process information
            self.processes[actual_spec.id] = process
            self.process_events[actual_spec.id] = (process_ready_event, shutdown_event)

            # Create a minimal wrapper for tracking purposes
            # This is NOT run in the main process - it's just for tracking
            tracking_wrapper = MultiProcessAgentWrapper(
                guild_spec=guild_spec,
                agent_spec=agent_spec,
                messaging_config=messaging_config,
                machine_id=machine_id,
                client_type=client_type,
                client_properties=client_properties,
            )
            tracking_wrapper.process = process

            # Add to tracking
            self.agent_tracker.add_agent(guild_id, actual_spec, tracking_wrapper)
            self.owned_agents.append((guild_id, actual_spec.id))

            # Update process info after successful start
            self.agent_tracker.update_process_info(guild_id, actual_spec.id)

            logging.info(f"Successfully started agent {actual_spec.id} in process {process.pid}")

        except Exception as e:
            logging.error(f"Failed to run agent {agent_spec.id if hasattr(agent_spec, 'id') else 'unknown'}: {e}")
            # Clean up on failure
            if hasattr(agent_spec, "id"):
                self.agent_tracker.remove_agent(guild_id, agent_spec.id)
                if agent_spec.id in self.processes:
                    del self.processes[agent_spec.id]
                    if agent_spec.id in self.process_events:
                        del self.process_events[agent_spec.id]
            raise

        return None  # We don't haave access to the agent here

    def stop_agent(self, guild_id: str, agent_id: str) -> None:
        """
        Stops an agent by signaling its process to shutdown.

        Args:
            guild_id: The ID of the guild containing the agent
            agent_id: The ID of the agent to stop
        """
        try:
            # Get the process and events
            process = self.processes.get(agent_id)
            events = self.process_events.get(agent_id)

            if process and events:
                process_ready_event: EventType
                shutdown_event: EventType
                process_ready_event, shutdown_event = events

                # Signal shutdown
                shutdown_event.set()

                # Wait for process to exit gracefully
                process.join(timeout=10)

                # Force terminate if needed
                if process.is_alive():
                    logging.warning(f"Agent {agent_id} did not shutdown gracefully, terminating")
                    process.terminate()
                    process.join(timeout=5)

                # Clean up
                del self.processes[agent_id]
                del self.process_events[agent_id]

                logging.info(f"Successfully stopped agent {agent_id}")
            else:
                logging.warning(f"Agent {agent_id} not found in processes")

            # Remove from tracking
            self.agent_tracker.remove_agent(guild_id, agent_id)

            # Remove from owned agents
            self.owned_agents = [
                (gid, aid) for gid, aid in self.owned_agents if not (gid == guild_id and aid == agent_id)
            ]

        except Exception as e:
            logging.error(f"Error stopping agent {agent_id}: {e}")
            raise

    def cleanup_dead_processes(self) -> None:
        """
        Clean up any dead processes.
        """
        dead_agents = []
        for agent_id, process in self.processes.items():
            if not process.is_alive():
                dead_agents.append(agent_id)

        for agent_id in dead_agents:
            logging.info(f"Cleaning up dead process for agent {agent_id}")
            # Find the guild_id for this agent
            guild_id = None
            for gid, aid in self.owned_agents:
                if aid == agent_id:
                    guild_id = gid
                    break

            if guild_id:
                self.stop_agent(guild_id, agent_id)

    def get_process_info(self, guild_id: str, agent_id: str) -> Dict[str, Any]:
        """
        Get process information for an agent.

        Args:
            guild_id: The ID of the guild containing the agent
            agent_id: The ID of the agent

        Returns:
            Dictionary containing process information
        """
        process = self.processes.get(agent_id)
        if process:
            return {
                "pid": process.pid,
                "is_alive": process.is_alive(),
                "name": process.name,
                "exitcode": process.exitcode,
            }
        return {}

    def shutdown(self) -> None:
        """
        Shutdown the execution engine and all managed agents.
        """
        logging.info("Shutting down MultiProcessExecutionEngine")

        # Stop all agents
        for guild_id, agent_id in self.owned_agents.copy():
            try:
                self.stop_agent(guild_id, agent_id)
            except Exception as e:
                logging.error(f"Error stopping agent {agent_id} during shutdown: {e}")

        # Force cleanup any remaining processes
        remaining_processes = list(self.processes.items())
        for agent_id, process in remaining_processes:
            try:
                if process.is_alive():
                    logging.warning(f"Force terminating remaining process for agent {agent_id}")
                    process.terminate()
                    process.join(timeout=2)
                    if process.is_alive():
                        logging.error(f"Force killing remaining process for agent {agent_id}")
                        process.kill()
                        process.join()
            except Exception as e:
                logging.error(f"Error force cleaning up process for agent {agent_id}: {e}")

        # Clear process tracking
        self.processes.clear()
        self.process_events.clear()
        self.owned_agents.clear()

        # Clean up agent tracker (this will shut down the multiprocessing manager)
        self.agent_tracker.clear()

        # Force cleanup any remaining active children (this is important for pytest)
        try:
            import multiprocessing

            active_children = multiprocessing.active_children()
            if active_children:
                logging.warning(f"Terminating {len(active_children)} remaining multiprocessing children")
                for child in active_children:
                    try:
                        child.terminate()
                        child.join(timeout=1)
                    except Exception as e:
                        logging.error(f"Error terminating child process {child.pid}: {e}")
        except Exception as e:
            logging.error(f"Error during final multiprocessing cleanup: {e}")

        logging.info("MultiProcessExecutionEngine shutdown complete")

    # Delegate methods to agent tracker
    def get_agents_in_guild(self, guild_id: str) -> Dict[str, AgentSpec]:
        """Get all agents in a guild."""
        return self.agent_tracker.get_agents_in_guild(guild_id)

    def find_agents_by_name(self, guild_id: str, name: str) -> List[AgentSpec]:
        """Find agents by name in a guild."""
        return self.agent_tracker.find_agents_by_name(guild_id, name)

    def is_agent_running(self, guild_id: str, agent_id: str) -> bool:
        """Check if an agent is running."""
        return self.agent_tracker.is_agent_alive(guild_id, agent_id)

    def get_engine_stats(self) -> Dict[str, Any]:
        """Get engine statistics."""
        base_stats = self.agent_tracker.get_stats()
        base_stats.update(
            {
                "engine_type": "MultiProcessExecutionEngine",
                "guild_id": self.guild_id,
                "max_processes": self.max_processes,
                "active_processes": len(self.processes),
                "owned_agents_count": len(self.owned_agents),
            }
        )
        return base_stats
