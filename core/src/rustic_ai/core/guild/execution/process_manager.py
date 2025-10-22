"""
Agent Process Manager

Guild-agnostic utility for managing agent processes.
Uses JSON serialization for security (not pickle).

This utility is reusable by both MultiProcessExecutionEngine (local)
and AgentHostServicer (K8s distributed execution).
"""

import json
import logging
import multiprocessing
import os
import signal
import time
from dataclasses import dataclass
from multiprocessing.synchronize import Event as EventType
from typing import Any, Dict, List, Optional, Type

from rustic_ai.core.guild.agent import AgentSpec
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.messaging import Client, MessageTrackingClient, MessagingConfig

logger = logging.getLogger(__name__)


@dataclass
class AgentProcessInfo:
    """Information about a running agent process."""

    agent_id: str
    guild_id: str
    pid: int
    is_alive: bool
    created_at: float
    agent_name: str = ""


def _agent_process_runner(
    agent_spec_json: str,
    guild_spec_json: str,
    messaging_config_json: str,
    machine_id: int,
    client_type_name: str,
    client_properties_json: str,
    process_ready_event: EventType,
    shutdown_event: EventType,
):
    """
    Function that runs in the child process to execute the agent wrapper.

    This uses JSON serialization instead of pickle for security.

    Args:
        agent_spec_json: JSON-serialized AgentSpec
        guild_spec_json: JSON-serialized GuildSpec
        messaging_config_json: JSON-serialized MessagingConfig
        machine_id: Machine ID for ID generation
        client_type_name: Name of the client class (e.g., "MessageTrackingClient")
        client_properties_json: JSON-serialized client properties
        process_ready_event: Event to signal process is ready
        shutdown_event: Event to signal shutdown
    """
    try:
        # Deserialize from JSON
        agent_spec_dict = json.loads(agent_spec_json)
        guild_spec_dict = json.loads(guild_spec_json)
        messaging_config_dict = json.loads(messaging_config_json)
        client_properties = json.loads(client_properties_json)

        # Reconstruct specs from dictionaries
        agent_spec = AgentSpec(**agent_spec_dict)
        guild_spec = GuildSpec(**guild_spec_dict)
        messaging_config = MessagingConfig(**messaging_config_dict)

        # Reconstruct the client type
        if client_type_name == "MessageTrackingClient":
            client_type = MessageTrackingClient
        else:
            # Default fallback
            client_type = MessageTrackingClient

        # Import the wrapper class
        from rustic_ai.core.guild.execution.multiprocess.multiprocess_agent_wrapper import MultiProcessAgentWrapper

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

        # Run the wrapper - this will call initialize_agent()
        wrapper.run()

    except Exception as e:
        logger.error(f"Error in agent process runner: {e}", exc_info=True)
        raise


class AgentProcessManager:
    """
    Reusable utility for managing agent processes.

    This utility is guild-agnostic and uses JSON serialization
    for security. It can be used by both local execution engines
    and the K8s agent host.

    Key features:
    - Process lifecycle management (spawn, stop, track)
    - JSON serialization (not pickle)
    - Guild-agnostic (takes guild_id per method)
    - Dead process cleanup
    - Graceful shutdown with timeout
    """

    def __init__(self, max_processes: int = 100):
        """
        Initialize the process manager.

        Args:
            max_processes: Maximum number of processes to allow
        """
        self.max_processes = max_processes

        # Track running processes
        self.processes: Dict[str, multiprocessing.Process] = {}
        self.process_info: Dict[str, AgentProcessInfo] = {}
        self.process_events: Dict[str, tuple[EventType, EventType]] = {}

        logger.info(f"AgentProcessManager initialized with max_processes={max_processes}")

    def spawn_agent_process(
        self,
        agent_spec: AgentSpec,
        guild_spec: GuildSpec,
        messaging_config: MessagingConfig,
        machine_id: int = 0,
        client_type_name: str = "MessageTrackingClient",
        client_properties: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Spawn a new agent process.

        Args:
            agent_spec: The agent specification
            guild_spec: The guild specification
            messaging_config: Configuration for messaging
            machine_id: Unique machine identifier
            client_type_name: Name of the client class
            client_properties: Properties for client initialization

        Returns:
            agent_id: The ID of the spawned agent

        Raises:
            RuntimeError: If max processes reached or spawn fails
        """
        if client_properties is None:
            client_properties = {}

        agent_id = agent_spec.id

        # Check if we're at the process limit
        if len(self.processes) >= self.max_processes:
            raise RuntimeError(f"Maximum number of processes ({self.max_processes}) reached")

        # Check if agent already exists
        if agent_id in self.processes:
            raise RuntimeError(f"Agent {agent_id} already exists")

        try:
            # Create events for process coordination
            process_ready_event = multiprocessing.Event()
            shutdown_event = multiprocessing.Event()

            # Serialize specs to JSON (secure alternative to pickle)
            agent_spec_json = agent_spec.model_dump_json()
            guild_spec_json = guild_spec.model_dump_json()
            messaging_config_json = messaging_config.model_dump_json()
            client_properties_json = json.dumps(client_properties)

            # Create and start the process
            process = multiprocessing.Process(
                target=_agent_process_runner,
                args=(
                    agent_spec_json,
                    guild_spec_json,
                    messaging_config_json,
                    machine_id,
                    client_type_name,
                    client_properties_json,
                    process_ready_event,
                    shutdown_event,
                ),
                name=f"Agent-{agent_id}",
            )

            process.start()

            # Wait for the process to be ready (with timeout)
            if not process_ready_event.wait(timeout=30):
                logger.error(f"Agent {agent_id} failed to start within timeout")
                process.terminate()
                process.join(timeout=5)
                raise RuntimeError(f"Agent {agent_id} failed to start within 30s")

            # Store process information
            self.processes[agent_id] = process
            self.process_events[agent_id] = (process_ready_event, shutdown_event)
            self.process_info[agent_id] = AgentProcessInfo(
                agent_id=agent_id,
                guild_id=guild_spec.id,
                pid=process.pid,
                is_alive=True,
                created_at=time.time(),
                agent_name=agent_spec.name,
            )

            logger.info(f"Successfully started agent {agent_id} in process {process.pid}")
            return agent_id

        except Exception as e:
            logger.error(f"Failed to spawn agent {agent_id}: {e}", exc_info=True)
            # Clean up on failure
            if agent_id in self.processes:
                del self.processes[agent_id]
            if agent_id in self.process_events:
                del self.process_events[agent_id]
            if agent_id in self.process_info:
                del self.process_info[agent_id]
            raise

    def stop_agent_process(self, agent_id: str, timeout: int = 10) -> bool:
        """
        Stop an agent process gracefully.

        Args:
            agent_id: The ID of the agent to stop
            timeout: Seconds to wait before force termination

        Returns:
            True if stopped successfully, False if agent not found
        """
        process = self.processes.get(agent_id)
        events = self.process_events.get(agent_id)

        if not process or not events:
            logger.warning(f"Agent {agent_id} not found in process manager")
            return False

        try:
            process_ready_event, shutdown_event = events

            # Signal shutdown
            shutdown_event.set()

            # Wait for process to exit gracefully
            process.join(timeout=timeout)

            # Force terminate if needed
            if process.is_alive():
                logger.warning(f"Agent {agent_id} did not shutdown gracefully, terminating")
                process.terminate()
                process.join(timeout=5)

                # Force kill if still alive
                if process.is_alive():
                    logger.error(f"Agent {agent_id} did not terminate, killing")
                    process.kill()
                    process.join(timeout=2)

            # Clean up
            del self.processes[agent_id]
            del self.process_events[agent_id]
            if agent_id in self.process_info:
                del self.process_info[agent_id]

            logger.info(f"Successfully stopped agent {agent_id}")
            return True

        except Exception as e:
            logger.error(f"Error stopping agent {agent_id}: {e}", exc_info=True)
            return False

    def is_process_alive(self, agent_id: str) -> bool:
        """
        Check if an agent process is alive.

        Args:
            agent_id: The ID of the agent

        Returns:
            True if process is alive, False otherwise
        """
        process = self.processes.get(agent_id)
        if process:
            is_alive = process.is_alive()
            # Update cached info
            if agent_id in self.process_info:
                self.process_info[agent_id].is_alive = is_alive
            return is_alive
        return False

    def get_process_info(self, agent_id: str) -> Optional[AgentProcessInfo]:
        """
        Get information about an agent process.

        Args:
            agent_id: The ID of the agent

        Returns:
            AgentProcessInfo if found, None otherwise
        """
        if agent_id not in self.process_info:
            return None

        # Update liveness
        process = self.processes.get(agent_id)
        if process:
            self.process_info[agent_id].is_alive = process.is_alive()

        return self.process_info[agent_id]

    def list_processes(self, guild_id: Optional[str] = None) -> Dict[str, AgentProcessInfo]:
        """
        List all managed processes.

        Args:
            guild_id: Optional filter by guild_id

        Returns:
            Dictionary mapping agent_id to AgentProcessInfo
        """
        # Update all liveness info
        for agent_id, process in self.processes.items():
            if agent_id in self.process_info:
                self.process_info[agent_id].is_alive = process.is_alive()

        if guild_id:
            return {aid: info for aid, info in self.process_info.items() if info.guild_id == guild_id}

        return self.process_info.copy()

    def cleanup_dead_processes(self) -> List[str]:
        """
        Clean up any dead processes.

        Returns:
            List of agent_ids that were cleaned up
        """
        dead_agents = []

        for agent_id, process in list(self.processes.items()):
            if not process.is_alive():
                dead_agents.append(agent_id)
                logger.info(f"Cleaning up dead process for agent {agent_id}")
                self.stop_agent_process(agent_id, timeout=1)

        return dead_agents

    def shutdown(self) -> None:
        """
        Shutdown all managed processes.
        """
        logger.info("Shutting down AgentProcessManager")

        # Stop all agents
        for agent_id in list(self.processes.keys()):
            try:
                self.stop_agent_process(agent_id, timeout=5)
            except Exception as e:
                logger.error(f"Error stopping agent {agent_id} during shutdown: {e}")

        # Force cleanup any remaining processes
        for agent_id, process in list(self.processes.items()):
            try:
                if process.is_alive():
                    logger.warning(f"Force terminating remaining process for agent {agent_id}")
                    process.terminate()
                    process.join(timeout=2)
                    if process.is_alive():
                        logger.error(f"Force killing remaining process for agent {agent_id}")
                        process.kill()
                        process.join()
            except Exception as e:
                logger.error(f"Error force cleaning up process for agent {agent_id}: {e}")

        # Clear tracking
        self.processes.clear()
        self.process_events.clear()
        self.process_info.clear()

        logger.info("AgentProcessManager shutdown complete")
