import logging
import multiprocessing
import pickle
from typing import Any, Dict, List, Optional

from rustic_ai.core.guild.agent import AgentSpec

from .multiprocess_agent_wrapper import MultiProcessAgentWrapper


class MultiProcessAgentTracker:
    """
    MultiProcessAgentTracker tracks agents that are running in separate processes.
    It uses multiprocessing.Manager to share data across processes safely.
    """

    def __init__(self) -> None:
        """
        Initializes the multiprocess agent tracker with shared data structures.
        """
        # Create a multiprocessing manager for shared data
        self.manager = multiprocessing.Manager()

        # Shared dictionaries for tracking agents across processes
        # Structure: {guild_id: {agent_id: (agent_spec_data, process_info)}}
        self.shared_agents: Any = self.manager.dict()

        # Shared dictionary for tracking agents by name
        # Structure: {guild_id: {agent_name: [agent_ids]}}
        self.shared_agents_by_name: Any = self.manager.dict()

        # Local tracking for agent wrappers (these can't be shared across processes)
        self.local_wrappers: Dict[str, MultiProcessAgentWrapper] = {}

    def add_agent(self, guild_id: str, agent_spec: AgentSpec, agent_wrapper: MultiProcessAgentWrapper) -> None:
        """
        Adds an agent to the multiprocess tracker.

        Args:
            guild_id: The ID of the guild the agent belongs to.
            agent_spec: The agent specification.
            agent_wrapper: The multiprocess agent wrapper.
        """
        try:
            # Serialize the agent spec for sharing
            agent_spec_data = pickle.dumps(agent_spec)

            # Create process info dictionary (PID will be updated later)
            process_info = {
                "pid": None,  # Will be updated after process starts
                "is_alive": False,  # Will be updated after process starts
                "agent_id": agent_spec.id,
                "agent_name": agent_spec.name,
            }

            # Add to shared agents tracking
            if guild_id not in self.shared_agents:
                self.shared_agents[guild_id] = self.manager.dict()

            self.shared_agents[guild_id][agent_spec.id] = (agent_spec_data, process_info)

            # Add to shared agents by name tracking
            if guild_id not in self.shared_agents_by_name:
                self.shared_agents_by_name[guild_id] = self.manager.dict()

            if agent_spec.name not in self.shared_agents_by_name[guild_id]:
                self.shared_agents_by_name[guild_id][agent_spec.name] = self.manager.list()

            self.shared_agents_by_name[guild_id][agent_spec.name].append(agent_spec.id)

            # Store wrapper locally (can't be shared across processes)
            wrapper_key = f"{guild_id}:{agent_spec.id}"
            self.local_wrappers[wrapper_key] = agent_wrapper

            logging.info(f"Added agent {agent_spec.id} to tracker for guild {guild_id}")

        except Exception as e:
            logging.error(f"Error adding agent {agent_spec.id} to tracker: {e}")
            raise

    def update_process_info(self, guild_id: str, agent_id: str) -> None:
        """
        Update the process info for an agent after it has started.

        Args:
            guild_id: The ID of the guild the agent belongs to.
            agent_id: The ID of the agent to update.
        """
        try:
            wrapper = self.get_agent_wrapper(guild_id, agent_id)
            if wrapper and guild_id in self.shared_agents and agent_id in self.shared_agents[guild_id]:
                agent_spec_data, old_process_info = self.shared_agents[guild_id][agent_id]

                # Update process info with current values
                updated_process_info = {
                    "pid": wrapper.get_process_id(),
                    "is_alive": wrapper.is_alive(),
                    "agent_id": agent_id,
                    "agent_name": old_process_info.get("agent_name", "Unknown"),
                }

                # Update in shared storage
                self.shared_agents[guild_id][agent_id] = (agent_spec_data, updated_process_info)

                logging.debug(f"Updated process info for agent {agent_id}: PID={updated_process_info['pid']}")

        except Exception as e:
            logging.error(f"Error updating process info for agent {agent_id}: {e}")

    def remove_agent(self, guild_id: str, agent_id: str) -> None:
        """
        Removes an agent from the multiprocess tracker.

        Args:
            guild_id: The ID of the guild the agent belongs to.
            agent_id: The ID of the agent to remove.
        """
        try:
            # Remove from shared agents tracking
            if guild_id in self.shared_agents and agent_id in self.shared_agents[guild_id]:
                del self.shared_agents[guild_id][agent_id]

                # Clean up empty guild entries
                if len(self.shared_agents[guild_id]) == 0:
                    del self.shared_agents[guild_id]

            # Remove from shared agents by name tracking
            if guild_id in self.shared_agents_by_name:
                for name, ids in self.shared_agents_by_name[guild_id].items():
                    if agent_id in ids:
                        ids.remove(agent_id)
                        # Clean up empty name entries
                        if len(ids) == 0:
                            del self.shared_agents_by_name[guild_id][name]
                        break

                # Clean up empty guild entries
                if len(self.shared_agents_by_name[guild_id]) == 0:
                    del self.shared_agents_by_name[guild_id]

            # Remove from local wrappers
            wrapper_key = f"{guild_id}:{agent_id}"
            if wrapper_key in self.local_wrappers:
                del self.local_wrappers[wrapper_key]

            logging.info(f"Removed agent {agent_id} from tracker for guild {guild_id}")

        except Exception as e:
            logging.error(f"Error removing agent {agent_id} from tracker: {e}")

    def get_agent_spec(self, guild_id: str, agent_id: str) -> Optional[AgentSpec]:
        """
        Retrieves an agent specification from the tracker.

        Args:
            guild_id: The ID of the guild the agent belongs to.
            agent_id: The ID of the agent to retrieve.

        Returns:
            AgentSpec: The agent specification, or None if not found.
        """
        try:
            if guild_id in self.shared_agents and agent_id in self.shared_agents[guild_id]:
                agent_spec_data, _ = self.shared_agents[guild_id][agent_id]
                return pickle.loads(agent_spec_data)
            return None
        except Exception as e:
            logging.error(f"Error retrieving agent spec for {agent_id}: {e}")
            return None

    def get_agent_wrapper(self, guild_id: str, agent_id: str) -> Optional[MultiProcessAgentWrapper]:
        """
        Retrieves an agent wrapper from the local tracker.

        Args:
            guild_id: The ID of the guild the agent belongs to.
            agent_id: The ID of the agent to retrieve.

        Returns:
            MultiProcessAgentWrapper: The agent wrapper, or None if not found.
        """
        wrapper_key = f"{guild_id}:{agent_id}"
        return self.local_wrappers.get(wrapper_key)

    def get_agents_in_guild(self, guild_id: str) -> Dict[str, AgentSpec]:
        """
        Returns the agents that are currently running in the guild.

        Args:
            guild_id: The ID of the guild

        Returns:
            Dict[str, AgentSpec]: A dictionary of agents that are currently running in the guild.
        """
        try:
            if guild_id not in self.shared_agents:
                return {}

            result = {}
            for agent_id, (agent_spec_data, process_info) in self.shared_agents[guild_id].items():
                try:
                    agent_spec = pickle.loads(agent_spec_data)

                    # Check if the process is still alive
                    wrapper = self.get_agent_wrapper(guild_id, agent_id)
                    if wrapper and wrapper.is_alive():
                        result[agent_id] = agent_spec
                    else:
                        # Process is dead, should be cleaned up
                        logging.warning(f"Found dead agent process for {agent_id}, cleaning up")
                        self.remove_agent(guild_id, agent_id)

                except Exception as e:
                    logging.error(f"Error processing agent {agent_id}: {e}")
                    continue

            return result

        except Exception as e:
            logging.error(f"Error getting agents in guild {guild_id}: {e}")
            return {}

    def find_agents_by_name(self, guild_id: str, agent_name: str) -> List[AgentSpec]:
        """
        Returns the agents that are currently running in the guild with the specified name.

        Args:
            guild_id: The ID of the guild
            agent_name: The name of the agent

        Returns:
            List[AgentSpec]: A list of agents that are currently running in the guild with the specified name.
        """
        try:
            if guild_id not in self.shared_agents_by_name or agent_name not in self.shared_agents_by_name[guild_id]:
                return []

            result = []
            agent_ids = list(self.shared_agents_by_name[guild_id][agent_name])

            for agent_id in agent_ids:
                try:
                    agent_spec = self.get_agent_spec(guild_id, agent_id)
                    if agent_spec:
                        # Check if the process is still alive
                        wrapper = self.get_agent_wrapper(guild_id, agent_id)
                        if wrapper and wrapper.is_alive():
                            result.append(agent_spec)
                        else:
                            # Process is dead, should be cleaned up
                            logging.warning(f"Found dead agent process for {agent_id}, cleaning up")
                            self.remove_agent(guild_id, agent_id)

                except Exception as e:
                    logging.error(f"Error processing agent {agent_id}: {e}")
                    continue

            return result

        except Exception as e:
            logging.error(f"Error finding agents by name {agent_name} in guild {guild_id}: {e}")
            return []

    def is_agent_alive(self, guild_id: str, agent_id: str) -> bool:
        """
        Check if an agent is alive and running.

        Args:
            guild_id: The ID of the guild the agent belongs to.
            agent_id: The ID of the agent to check.

        Returns:
            bool: True if the agent is alive and running, False otherwise.
        """
        wrapper = self.get_agent_wrapper(guild_id, agent_id)
        return wrapper is not None and wrapper.is_alive()

    def get_process_info(self, guild_id: str, agent_id: str) -> Optional[Dict]:
        """
        Get process information for an agent.

        Args:
            guild_id: The ID of the guild the agent belongs to.
            agent_id: The ID of the agent.

        Returns:
            Dict: Process information, or None if not found.
        """
        try:
            if guild_id in self.shared_agents and agent_id in self.shared_agents[guild_id]:
                _, process_info = self.shared_agents[guild_id][agent_id]
                return dict(process_info)  # Convert from managed dict
            return None
        except Exception as e:
            logging.error(f"Error getting process info for {agent_id}: {e}")
            return None

    def clear(self) -> None:
        """
        Clears the tracker and shuts down all tracked agents.
        """
        try:
            # Shutdown all agent wrappers
            for wrapper in list(self.local_wrappers.values()):
                try:
                    wrapper.shutdown()
                except Exception as e:
                    logging.error(f"Error shutting down wrapper: {e}")

            # Clear local tracking
            self.local_wrappers.clear()

            # Clear shared tracking
            self.shared_agents.clear()
            self.shared_agents_by_name.clear()

            # CRITICAL: Shut down the multiprocessing manager process
            # This is what prevents pytest from hanging - the manager creates a background process
            if hasattr(self, "manager") and self.manager:
                try:
                    self.manager.shutdown()
                    # Don't set to None as it breaks type checking, just mark as shut down
                    self._manager_shutdown = True
                except Exception as e:
                    logging.warning(f"Error shutting down multiprocessing manager: {e}")

            logging.info("Cleared multiprocess agent tracker")

        except Exception as e:
            logging.error(f"Error clearing agent tracker: {e}")

    def get_stats(self) -> Dict:
        """
        Get statistics about tracked agents.

        Returns:
            Dict: Statistics about the tracker.
        """
        try:
            # Ensure manager is initialized
            if self.manager is None:
                self.manager = multiprocessing.Manager()
                self.shared_agents = self.manager.dict()
                self.shared_agents_by_name = self.manager.dict()

            # Ensure shared data structures are initialized
            if self.shared_agents is None:
                self.shared_agents = self.manager.dict()
            if self.shared_agents_by_name is None:
                self.shared_agents_by_name = self.manager.dict()

            # Safely get values with fallback
            try:
                total_agents = sum(len(guild_agents) for guild_agents in self.shared_agents.values())
                total_guilds = len(self.shared_agents)
            except (AttributeError, TypeError):
                # Fallback if shared_agents is still None or invalid
                total_agents = 0
                total_guilds = 0

            # For alive_agents count, we need to use a different approach since local_wrappers
            # is not available in the manager context. We'll use the get_agents_in_guild method
            # which properly checks if agents are alive
            alive_agents = 0
            try:
                for guild_id in self.shared_agents:
                    alive_agents += len(self.get_agents_in_guild(guild_id))
            except (AttributeError, TypeError):
                # Fallback if iteration fails
                alive_agents = 0

            return {
                "total_agents": total_agents,
                "alive_agents": alive_agents,
                "total_guilds": total_guilds,
                "local_wrappers": len(self.local_wrappers),
            }

        except Exception as e:
            logging.error(f"Error getting tracker stats: {e}")
            # Return basic stats even if there's an error
            return {
                "total_agents": 0,
                "alive_agents": 0,
                "total_guilds": 0,
                "local_wrappers": len(self.local_wrappers) if hasattr(self, "local_wrappers") else 0,
                "error": str(e),
            }
