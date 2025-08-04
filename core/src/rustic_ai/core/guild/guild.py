import logging
from textwrap import dedent
from typing import Any, Dict, List, Optional, Type

from rustic_ai.core.guild import GSKC, Agent, AgentSpec, GuildSpec
from rustic_ai.core.guild.dsl import DependencySpec
from rustic_ai.core.guild.execution import ExecutionEngine
from rustic_ai.core.guild.execution.sync.sync_exec_engine import SyncExecutionEngine
from rustic_ai.core.messaging import MessageTrackingClient, MessagingConfig
from rustic_ai.core.messaging.core.client import Client
from rustic_ai.core.messaging.core.message import RoutingSlip
from rustic_ai.core.utils.class_utils import create_execution_engine


class Guild:
    def __init__(
        self,
        id: str,
        name: str,
        description: str,
        organization_id: str,
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
            execution_engine_clz: The execution engine class to run agents within the guild.
            messaging_config: MessagingConfig to initialize MessagingInterface for communication between agents.
            client_type: The default client type for agents within the guild.
            client_properties: Default properties for initializing clients for the agents.
        """
        self.id = id
        self.name = name
        self.description = description
        self.organization_id = organization_id
        self.execution_engine = create_execution_engine(
            execution_engine_clz, guild_id=id, organization_id=organization_id
        )
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
            agent_spec: The agent to add and run.
        """
        assert isinstance(agent_spec, AgentSpec), "agent_spec must be an instance of AgentSpec"
        self._internal_add_agent(agent_spec, execution_engine)

    def register_or_launch_agent(self, agent_spec: AgentSpec):
        """
        Registers an agent with the guild and uses the execution engine to run it.
        """
        if not self.execution_engine.is_agent_running(self.id, agent_spec.id):
            logging.info(f"Launching agent {agent_spec.name} in guild {self.name}")
            self.launch_agent(agent_spec, self.execution_engine)
        else:
            logging.info(f"Registering agent {agent_spec.name} in guild {self.name}")
            self.register_agent(agent_spec)

    def _add_local_agent(self, agent_spec: AgentSpec, execution_engine: Optional[ExecutionEngine] = None) -> Agent:
        """
        Adds a local agent to the guild and uses the execution engine to run it.
        NOTE: This method is only to facilitate testing. Should never be used in production.
        Hence, this method is intentionally marked as private.

        Parameters:
            agent_spec: The agent_spec to instantiate the agent from.
            execution_engine: The execution engine to run the agent with.
        """
        assert isinstance(agent_spec, AgentSpec), "agent_spec must be an instance of AgentSpec"
        if execution_engine is None:
            execution_engine = SyncExecutionEngine(guild_id=self.id, organization_id=self.organization_id)
        return self._internal_add_agent(agent_spec, execution_engine)

    def _internal_add_agent(
        self, agent_spec: AgentSpec, execution_engine: Optional[ExecutionEngine] = None
    ) -> Optional[Agent]:
        self.register_agent(agent_spec)
        # Increment the machine ID for unique ID generation
        self.last_machine_id += 1

        agent: Optional[Agent] = None
        if execution_engine is None:
            execution_engine = self.execution_engine
        else:
            self.agent_exec_engines[agent_spec.id] = execution_engine

        logging.info(f"Running agent {agent_spec.name} in guild {self.name}")

        logging.info(
            dedent(
                f"""-----------------------------------------
                   Execution engine: {execution_engine}
                   Messaging: {self.messaging}
                   Client Type: {self.client_type}
                   Client Properties: {self.client_properties}
                   Default Topic: {self.DEFAULT_TOPIC}
                   -----------------------------------------"""
            )
        )

        # Check if the agent is already running before running it
        if not execution_engine.is_agent_running(guild_id=self.id, agent_id=agent_spec.id):
            try:
                agent = execution_engine.run_agent(
                    agent_spec=agent_spec,
                    guild_spec=self.to_spec(),
                    messaging_config=self.messaging,
                    machine_id=self.last_machine_id,
                    client_type=self.client_type,
                    client_properties=self.client_properties,
                    default_topic=self.DEFAULT_TOPIC,
                )
                logging.info(f"Agent {agent_spec.name} started successfully")

            except Exception as e:
                logging.error(f"Error running agent {agent_spec.name}: {e}")
                raise e

        else:
            logging.warning(f"Agent {agent_spec.name} is already running")

        return agent

    def get_agent_count(self) -> int:
        """
        Retrieves the number of agents in the guild.

        Returns:
            The number of agents in the guild.
        """
        return len(self._agents_by_id)

    def is_agent_running(self, agent_id: str) -> bool:
        """
        Checks if the guild is running.
        """
        return self.execution_engine.is_agent_running(self.id, agent_id)

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
                GSKC.CLIENT_TYPE: self.client_type.get_qualified_class_name(),
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
        Shuts down the execution engines associated with all the agents and the guild itself.
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

    def is_guild_running(self):
        for agent in self._agents_by_id.keys():
            if not self.execution_engine.is_agent_running(self.id, agent):
                return False
        else:
            return True
