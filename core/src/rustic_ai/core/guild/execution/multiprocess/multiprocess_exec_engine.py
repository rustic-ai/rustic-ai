import logging
import multiprocessing
from typing import Any, Dict, List, Optional, Type, Union

from rustic_ai.core.guild.agent import Agent, AgentSpec
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.guild.execution.execution_engine import ExecutionEngine
from rustic_ai.core.messaging import Client, MessageTrackingClient, MessagingConfig

from .agent_tracker import MultiProcessAgentTracker
from .multiprocess_agent_wrapper import MultiProcessAgentWrapper


class MultiProcessExecutionEngine(ExecutionEngine):
    """
    An execution engine that runs agents in separate processes for true parallelism.
    This escapes the Python GIL and allows for genuine concurrent execution.

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
            organization_id: The ID of the organization this engine belongs to
            max_processes: Maximum number of processes to use (defaults to CPU count)
        """
        super().__init__(guild_id=guild_id, organization_id=organization_id)

        # Set multiprocessing start method to 'spawn' for better cross-platform compatibility
        # and to avoid issues with shared state
        try:
            multiprocessing.set_start_method("spawn", force=True)
        except RuntimeError:
            # Start method already set, ignore
            pass

        self.max_processes = max_processes or multiprocessing.cpu_count()
        self.agent_tracker = MultiProcessAgentTracker()
        self.owned_agents: List[tuple[str, str]] = []

        logging.info(f"Initialized MultiProcessExecutionEngine with max_processes={self.max_processes}")

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
        Creates a MultiProcessAgentWrapper for the agent and runs it in a separate process.

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

            # Create the agent wrapper
            agent_wrapper = MultiProcessAgentWrapper(
                guild_spec=guild_spec,
                agent_spec=agent_spec,
                messaging_config=messaging_config,
                machine_id=machine_id,
                client_type=client_type,
                client_properties=client_properties,
            )

            # Add to tracking before starting to avoid race conditions
            self.agent_tracker.add_agent(guild_id, actual_spec, agent_wrapper)
            self.owned_agents.append((guild_id, actual_spec.id))

            # Start the agent process
            agent_wrapper.run()

            # Update process info after successful start
            self.agent_tracker.update_process_info(guild_id, actual_spec.id)

            logging.info(f"Successfully started agent {actual_spec.id} in process {agent_wrapper.get_process_id()}")

        except Exception as e:
            logging.error(f"Failed to run agent {agent_spec.id if hasattr(agent_spec, 'id') else 'unknown'}: {e}")
            # Clean up on failure
            if hasattr(agent_spec, "id"):
                self.agent_tracker.remove_agent(guild_id, agent_spec.id)
                try:
                    self.owned_agents.remove((guild_id, agent_spec.id))
                except ValueError:
                    pass
            raise

    def get_agents_in_guild(self, guild_id: str) -> Dict[str, AgentSpec]:
        """
        Returns all agents currently running in the specified guild.

        Args:
            guild_id: The ID of the guild

        Returns:
            Dict[str, AgentSpec]: Dictionary mapping agent IDs to their specifications
        """
        return self.agent_tracker.get_agents_in_guild(guild_id)

    def is_agent_running(self, guild_id: str, agent_id: str) -> bool:
        """
        Checks if an agent is currently running in the specified guild.

        Args:
            guild_id: The ID of the guild
            agent_id: The ID of the agent to check

        Returns:
            bool: True if the agent is running, False otherwise
        """
        return self.agent_tracker.is_agent_alive(guild_id, agent_id)

    def find_agents_by_name(self, guild_id: str, agent_name: str) -> List[AgentSpec]:
        """
        Returns all agents in the guild with the specified name.

        Args:
            guild_id: The ID of the guild
            agent_name: The name to search for

        Returns:
            List[AgentSpec]: List of agent specifications matching the name
        """
        return self.agent_tracker.find_agents_by_name(guild_id, agent_name)

    def stop_agent(self, guild_id: str, agent_id: str) -> None:
        """
        Stops an agent that is currently running.

        Args:
            guild_id: The ID of the guild the agent belongs to
            agent_id: The ID of the agent to stop
        """
        try:
            # Get the agent wrapper
            agent_wrapper = self.agent_tracker.get_agent_wrapper(guild_id, agent_id)

            if agent_wrapper is not None:
                logging.info(f"Stopping agent {agent_id} in guild {guild_id}")

                # Shutdown the agent process
                agent_wrapper.shutdown()

                # Remove from tracking
                self.agent_tracker.remove_agent(guild_id, agent_id)

                # Remove from owned agents
                try:
                    self.owned_agents.remove((guild_id, agent_id))
                except ValueError:
                    logging.warning(f"Agent {agent_id} not found in owned agents list")

                logging.info(f"Successfully stopped agent {agent_id}")
            else:
                logging.warning(f"Agent {agent_id} not found in guild {guild_id}")

        except Exception as e:
            logging.error(f"Error stopping agent {agent_id}: {e}")

    def shutdown(self) -> None:
        """
        Shutdown the execution engine and all running agents.
        """
        try:
            logging.info(f"Shutting down MultiProcessExecutionEngine with {len(self.owned_agents)} agents")

            # Stop all owned agents
            for guild_id, agent_id in list(self.owned_agents):
                try:
                    self.stop_agent(guild_id, agent_id)
                except Exception as e:
                    logging.error(f"Error stopping agent {agent_id} during shutdown: {e}")

            # Clear the tracker
            self.agent_tracker.clear()

            # Clear owned agents list
            self.owned_agents.clear()

            logging.info("MultiProcessExecutionEngine shutdown complete")

        except Exception as e:
            logging.error(f"Error during execution engine shutdown: {e}")

    def get_process_info(self, guild_id: str, agent_id: str) -> Dict:
        """
        Get process information for a specific agent.

        Args:
            guild_id: The ID of the guild the agent belongs to
            agent_id: The ID of the agent

        Returns:
            Dict: Process information including PID, status, etc.
        """
        return self.agent_tracker.get_process_info(guild_id, agent_id) or {}

    def get_engine_stats(self) -> Dict:
        """
        Get statistics about the execution engine.

        Returns:
            Dict: Statistics including agent counts, process info, etc.
        """
        try:
            stats = self.agent_tracker.get_stats()
            stats.update(
                {
                    "engine_type": "MultiProcessExecutionEngine",
                    "guild_id": self.guild_id,
                    "max_processes": self.max_processes,
                    "owned_agents_count": len(self.owned_agents),
                }
            )
            return stats
        except Exception as e:
            logging.error(f"Error getting engine stats: {e}")
            return {"error": str(e)}

    def cleanup_dead_processes(self) -> None:
        """
        Clean up any dead agent processes that may have crashed.
        This is called automatically by some methods but can be called manually.
        """
        try:
            # Get all agents and check if they're alive
            dead_agents = []
            for guild_id, agent_id in self.owned_agents:
                if not self.agent_tracker.is_agent_alive(guild_id, agent_id):
                    dead_agents.append((guild_id, agent_id))

            # Clean up dead agents
            for guild_id, agent_id in dead_agents:
                logging.warning(f"Cleaning up dead agent process: {agent_id}")
                self.agent_tracker.remove_agent(guild_id, agent_id)
                try:
                    self.owned_agents.remove((guild_id, agent_id))
                except ValueError:
                    pass

            if dead_agents:
                logging.info(f"Cleaned up {len(dead_agents)} dead agent processes")

        except Exception as e:
            logging.error(f"Error during cleanup of dead processes: {e}")

    def __del__(self):
        """
        Ensure cleanup on destruction.
        """
        try:
            self.shutdown()
        except Exception:
            pass  # Ignore errors during destruction
