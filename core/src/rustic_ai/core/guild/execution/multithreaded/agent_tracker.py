from typing import Dict, List, Optional, Tuple

from rustic_ai.core.guild.agent import AgentSpec
from rustic_ai.core.guild.execution.multithreaded.multithreaded_agent_wrapper import (
    MultiThreadedAgentWrapper,
)

# This is a dictionary that keeps track of all the agents that are currently running in the system.
# The keys are guild IDs, and the values are dictionaries that map agent IDs to their corresponding agent specifications and multithreaded agent wrappers.
inmem_mt_all_agents: Dict[str, Dict[str, Tuple[AgentSpec, MultiThreadedAgentWrapper]]] = {}

# This is a dictionary that keeps track of names of agents that are currently running in the system.
# The keys are guild IDs, and the values are dictionaries that map agent names to lists of agent IDs.
inmem_mt_agents_by_name: Dict[str, Dict[str, List[str]]] = {}


class InMemoryMTAgentTracker:
    """
    InMemoryMTAgentTracker is a simple in-memory tracker for agents that are currently running in the system.

    Attributes:
        - agents (Dict[str, Dict[str, (AgentSpec, MultiThreadedAgentWrapper)]]): A dictionary that maps guild IDs to
            dictionaries that map agent IDs to their corresponding agent specifications and synchronous agent wrappers.
    """

    def __init__(self) -> None:
        """
        Initializes the in-memory agent tracker with an empty dictionary.
        """
        self.agents: Dict[str, Dict[str, Tuple[AgentSpec, MultiThreadedAgentWrapper]]] = {}

    def add_agent(self, guild_id: str, agent_spec: AgentSpec, agent_wrapper: MultiThreadedAgentWrapper) -> None:
        """
        Adds an agent to the in-memory tracker.

        Args:
            guild_id (str): The ID of the guild the agent belongs to.
            agent_spec (AgentSpec): The agent specification.
            agent_wrapper (MultiThreadedAgentWrapper): The synchronous agent wrapper.
        """

        # Track in local records
        if guild_id not in self.agents:
            self.agents[guild_id] = {}

        self.agents[guild_id][agent_spec.id] = (agent_spec, agent_wrapper)

        # Track in global records
        if guild_id not in inmem_mt_all_agents:
            inmem_mt_all_agents[guild_id] = {}

        inmem_mt_all_agents[guild_id][agent_spec.id] = (agent_spec, agent_wrapper)

        # Track by name
        if guild_id not in inmem_mt_agents_by_name:
            inmem_mt_agents_by_name[guild_id] = {}

        if agent_spec.name not in inmem_mt_agents_by_name[guild_id]:
            inmem_mt_agents_by_name[guild_id][agent_spec.name] = []

        inmem_mt_agents_by_name[guild_id][agent_spec.name].append(agent_spec.id)

    def remove_agent(self, guild_id: str, agent_id: str) -> None:
        """
        Removes an agent from the in-memory tracker.

        Args:
            guild_id (str): The ID of the guild the agent belongs to.
            agent_id (str): The ID of the agent to remove.
        """
        # Remove from local records
        if guild_id in self.agents and agent_id in self.agents[guild_id]:
            del self.agents[guild_id][agent_id]

        # Remove from global records
        if guild_id in inmem_mt_all_agents and agent_id in inmem_mt_all_agents[guild_id]:
            del inmem_mt_all_agents[guild_id][agent_id]

        # Remove from name records
        if guild_id in inmem_mt_agents_by_name:
            for name, ids in inmem_mt_agents_by_name[guild_id].items():
                if agent_id in ids:
                    ids.remove(agent_id)
                    break

    def get_agent_spec(self, guild_id: str, agent_id: str) -> Optional[AgentSpec]:  # pragma: no cover
        """
        Retrieves an agent from the in-memory tracker.

        Args:
            guild_id (str): The ID of the guild the agent belongs to.
            agent_id (str): The ID of the agent to retrieve.

        Returns:
            AgentSpec: The agent specification.
        """
        if guild_id in inmem_mt_all_agents and agent_id in inmem_mt_all_agents[guild_id]:
            return inmem_mt_all_agents[guild_id][agent_id][0]

        return None

    def get_agent_wrapper(self, guild_id: str, agent_id: str) -> Optional[MultiThreadedAgentWrapper]:
        """
        Retrieves an agent from the in-memory tracker.

        Args:
            guild_id (str): The ID of the guild the agent belongs to.
            agent_id (str): The ID of the agent to retrieve.

        Returns:
            MultiThreadedAgentWrapper: The synchronous agent wrapper.
        """
        if guild_id in inmem_mt_all_agents and agent_id in inmem_mt_all_agents[guild_id]:
            return inmem_mt_all_agents[guild_id][agent_id][1]

        return None

    def get_agents_in_guild(self, guild_id: str) -> Dict[str, AgentSpec]:
        """
        Returns the agents that are currently running in the guild.

        Args:
            guild_id: The ID of the guild

        Returns:
            Dict[str, AgentSpec]: A dictionary of agents that are currently running in the guild.
        """
        if guild_id in inmem_mt_all_agents:
            return {agent_id: agent_spec for agent_id, (agent_spec, _) in inmem_mt_all_agents[guild_id].items()}

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
        if guild_id in inmem_mt_agents_by_name and agent_name in inmem_mt_agents_by_name[guild_id]:
            return [
                inmem_mt_all_agents[guild_id][agent_id][0] for agent_id in inmem_mt_agents_by_name[guild_id][agent_name]
            ]

        return []

    def clear(self) -> None:
        """
        Clears the in-memory tracker.
        """
        self.agents.clear()
        inmem_mt_all_agents.clear()
        inmem_mt_agents_by_name.clear()
