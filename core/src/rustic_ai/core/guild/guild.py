from typing import Any, Dict, List, Optional, Type, Union

from rustic_ai.core.guild import GSKC, Agent, AgentSpec, GuildSpec
from rustic_ai.core.guild.dsl import DependencySpec
from rustic_ai.core.guild.execution import ExecutionEngine
from rustic_ai.core.messaging import MessageTrackingClient, MessagingConfig
from rustic_ai.core.messaging.core.client import Client
from rustic_ai.core.messaging.core.message import RoutingSlip
from rustic_ai.core.utils.class_utils import create_execution_engine


class Guild:
    """
    A class representing a guild of agents, updated to use a pluggable ExecutionEngine.
    """

    def __init__(
        self,
        id: str,
        name: str,
        description: str,
        execution_engine_clz: str,
        messaging_config: MessagingConfig,
        client_type: Type[Client] = MessageTrackingClient,
        client_properties: Dict[str, Any] = {},
        dependency_map: Dict[str, DependencySpec] = {},
        routes: RoutingSlip = RoutingSlip(),
    ):
        """
        Initializes a new instance of the Guild class with an execution engine.

        Parameters:
            id: The ID of the guild.
            name: The name of the guild.
            description: A description of the guild.
            execution_engine: The execution engine to run agents within the guild.
            messaging: Either an instance of MessagingInterface or a configuration
                to initialize one to use for communication between agents.
            client_type: The default client type for agents within the guild.
            client_properties: Default properties for initializing clients for the agents.
        """
        self.id = id
        self.name = name
        self.description = description
        self.execution_engine = create_execution_engine(execution_engine_clz, guild_id=id)
        self.messaging = messaging_config
        self.client_type = client_type
        self.client_properties = client_properties
        self._agents_by_id: Dict[str, AgentSpec] = {}
        self._agents_by_name: Dict[str, AgentSpec] = {}
        self.last_machine_id = 0
        self.agent_exec_engines: Dict[str, ExecutionEngine] = {}
        self.dependency_map = dependency_map
        self.routes = routes

    DEFAULT_TOPIC = "default_topic"

    def register_agent(self, agent_spec: AgentSpec):
        """
        Registers an agent with the guild, but does not run it.

        Parameters:
            agent_spec: The agent to register.
        """
        self._agents_by_id[agent_spec.id] = agent_spec
        self._agents_by_name[agent_spec.name] = agent_spec

    def launch_agent(self, agent_spec: AgentSpec, execution_engine: Optional[ExecutionEngine] = None):
        """
        Adds an agent to the guild and uses the execution engine to run it.

        Parameters:
            agent: The agent to add and run.
        """
        assert isinstance(agent_spec, AgentSpec), "agent_spec must be an instance of AgentSpec"
        self._internal_add_agent(agent_spec, execution_engine)

    def _add_local_agent(self, agent: Agent, execution_engine: Optional[ExecutionEngine] = None):
        """
        Adds a local agent to the guild and uses the execution engine to run it.
        NOTE: This method is only to facilitate testing. Should never be used in production.
        Hence, this method is intentionally marked as private.

        Parameters:
            agent: The agent to add and run.
            execution_engine: The execution engine to run the agent with.
        """
        assert isinstance(agent, Agent), "agent must be an instance of Agent"
        self._internal_add_agent(agent, execution_engine)

    def _internal_add_agent(
        self,
        agent_spec: Union[AgentSpec, Agent],
        execution_engine: Optional[ExecutionEngine] = None,
    ):
        agent_spec_obj = agent_spec if isinstance(agent_spec, AgentSpec) else agent_spec.get_spec()
        self.register_agent(agent_spec_obj)
        # Increment the machine ID for unique ID generation
        self.last_machine_id += 1

        if execution_engine is None:
            execution_engine = self.execution_engine
        else:
            self.agent_exec_engines[agent_spec.id] = execution_engine

        # Check if the agent is already running before running it
        if not execution_engine.is_agent_running(guild_id=self.id, agent_id=agent_spec.id):
            execution_engine.run_agent(
                agent_spec=agent_spec,
                guild_spec=self.to_spec(),
                messaging_config=self.messaging,
                machine_id=self.last_machine_id,
                client_type=self.client_type,
                client_properties=self.client_properties,
                default_topic=self.DEFAULT_TOPIC,
            )

    def get_agent_count(self) -> int:
        """
        Retrieves the number of agents in the guild.

        Returns:
            The number of agents in the guild.
        """
        return len(self._agents_by_id)

    def remove_agent(self, agent_id: str):
        """
        Removes an agent from the guild.

        Parameters:
            agent_id: The ID of the agent to remove.
        """
        if agent_id in self._agents_by_id:
            self.execution_engine.stop_agent(self.id, agent_id)
            agent_name = self._agents_by_id[agent_id].name
            del self._agents_by_name[agent_name]
            del self._agents_by_id[agent_id]
        else:
            raise ValueError(f"Agent with ID {agent_id} not found in guild")

    def get_agent(self, agent_id: str) -> Optional[AgentSpec]:
        """
        Retrieves an agent by its ID.

        Parameters:
            agent_id: The ID of the agent to retrieve.

        Returns:
            The agent with the specified ID, if it exists.
        """
        return self._agents_by_id.get(agent_id)

    def list_agents(self) -> List[AgentSpec]:
        """
        Lists all agents in the guild.

        Returns:
            A list of all agents in the guild.
        """
        return list(self._agents_by_id.values())

    def to_spec(self) -> GuildSpec:
        """
        Retrieves detailed information about the guild, including its agents.

        Returns:
            A GuildSpec object containing detailed information about the guild.
        """

        return GuildSpec(
            id=self.id,
            name=self.name,
            description=self.description,
            properties={
                GSKC.EXECUTION_ENGINE: self.execution_engine.get_qualified_class_name(),
                GSKC.MESSAGING: self.messaging,
                GSKC.CLIENT_TYPE: self.client_type,
                GSKC.CLIENT_PROPERTIES: self.client_properties,
            },
            agents=self.list_agents(),
            routes=self.routes,
            dependency_map=self.dependency_map,
        )

    def get_agent_by_name(self, name: str) -> Optional[AgentSpec]:
        """
        Retrieves an agent by its name.

        Parameters:
            name: The name of the agent to retrieve.

        Returns:
            The agent with the specified name, if it exists.
        """
        return self._agents_by_name.get(name)

    def shutdown(self):
        """
        Shuts down the guild and all of its agents.
        """
        for execution_engine in self.agent_exec_engines.values():
            execution_engine.shutdown()
        self.execution_engine.shutdown()

    def _get_execution_engine(self) -> ExecutionEngine:
        """
        Retrieves the execution engine for the guild.

        Returns:
            The execution engine for the guild.
        """
        return self.execution_engine

    def list_all_running_agents(self) -> List[AgentSpec]:
        """
        Retrieves all agents that are currently running.

        Returns:
            A list of all agents that are currently running.
        """
        return list(self.execution_engine.get_agents_in_guild(self.id).values())
