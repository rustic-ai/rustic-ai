from enum import StrEnum
from inspect import isclass
import json
import logging
import os
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Self,
    Type,
    TypeVar,
    Union,
)

import chevron
from pydantic import BaseModel
import shortuuid
import yaml

from rustic_ai.core.guild import Agent, Guild
from rustic_ai.core.guild.agent_ext.mixins.health import HealthConstants
from rustic_ai.core.guild.dsl import (
    APT,
    AgentSpec,
    BaseAgentProps,
    DependencySpec,
    GuildSpec,
    GuildTopics,
)
from rustic_ai.core.guild.dsl import (
    RuntimePredicate,
)
from rustic_ai.core.guild.dsl import KeyConstants as GSKC
from rustic_ai.core.guild.execution import SyncExecutionEngine
from rustic_ai.core.guild.metaprog.constants import MetaclassConstants
from rustic_ai.core.messaging import Client, MessageTrackingClient, MessagingConfig
from rustic_ai.core.messaging.core.message import (
    AgentTag,
    FunctionalTransformer,
    PayloadTransformer,
    ProcessStatus,
    RoutingRule,
    RoutingSlip,
    StateTransformer,
    TransformationType,
)
from rustic_ai.core.state.manager.in_memory_state_manager import InMemoryStateManager
from rustic_ai.core.state.manager.state_manager import (
    StateUpdateActions,
    StateUpdateFormat,
)
from rustic_ai.core.utils import class_utils
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.jexpr import JxScript


class OriginFilterKeys(StrEnum):
    ORIGIN_SENDER = "origin_sender"
    ORIGIN_TOPIC = "origin_topic"
    ORIGIN_MESSAGE_FORMAT = "origin_message_format"


class DestinationKeys(StrEnum):
    TOPICS = "topics"
    RECIPIENT_LIST = "recipient_list"
    PRIORITY = "priority"


class RoutingKeys(StrEnum):
    AGENT = "agent"
    AGENT_TYPE = "agent_type"
    METHOD_NAME = "method_name"
    ORIGIN_FILTER = "origin_filter"
    MESSAGE_FORMAT = "message_format"
    DESTINATION = "destination"
    MARK_FORWARDED = "mark_forwarded"
    ROUTE_TIMES = "route_times"
    PROCESS_STATUS = "process_status"
    TRANSFORMER = "transformer"
    REASON = "reason"


class KeyConstants:
    """
    Constants used in keys for AgentBuilder and GuildBuilder.
    """

    ID = "id"
    NAME = "name"
    DESCRIPTION = "description"
    CLASS_NAME = "class_name"
    ADDITIONAL_TOPICS = "additional_topics"
    PROPERTIES = "properties"
    AGENTS = "agents"
    LISTEN_TO_DEFAULT_TOPIC = "listen_to_default_topic"
    DEPENDENCY_MAP = "dependency_map"
    ROUTES = "routes"
    ACT_ONLY_WHEN_TAGGED = "act_only_when_tagged"
    PREDICATES = "predicates"
    CONFIGURATION = "configuration"
    CONFIGURATION_SCHEMA = "configuration_schema"


class EnvConstants:
    """
    Constants for environment variables.
    """

    RUSTIC_AI_MESSAGING_MODULE = "RUSTIC_AI_MESSAGING_MODULE"
    RUSTIC_AI_MESSAGING_CLASS = "RUSTIC_AI_MESSAGING_CLASS"
    RUSTIC_AI_MESSAGING_BACKEND_CONFIG = "RUSTIC_AI_MESSAGING_BACKEND_CONFIG"
    RUSTIC_AI_EXECUTION_ENGINE = "RUSTIC_AI_EXECUTION_ENGINE"
    RUSTIC_AI_CLIENT_TYPE = "RUSTIC_AI_CLIENT_TYPE"
    RUSTIC_AI_CLIENT_PROPERTIES = "RUSTIC_AI_CLIENT_PROPERTIES"
    RUSTIC_AI_DEPENDENCY_CONFIG = "RUSTIC_AI_DEPENDENCY_CONFIG"
    RUSTIC_AI_STATE_MANAGER = "RUSTIC_AI_STATE_MANAGER"
    RUSTIC_AI_STATE_MANAGER_CONFIG = "RUSTIC_AI_STATE_MANAGER_CONFIG"


AT = TypeVar("AT", bound=Agent, covariant=True)


class AgentBuilder(Generic[AT, APT]):  # type: ignore
    """
    Builder class for AgentSpec
    """

    def __init__(self, agent_type: Type[AT]):
        """
        Initialize the AgentBuilder.
        """
        self.agent_type: Type[AT] = agent_type
        self.agent_props_type: Type[APT] | dict = getattr(
            agent_type, MetaclassConstants.AGENT_PROPS_TYPE, BaseAgentProps
        )

        self.agent_spec_dict: dict = {
            KeyConstants.ID: shortuuid.uuid(),
            KeyConstants.NAME: None,
            KeyConstants.DESCRIPTION: None,
            KeyConstants.CLASS_NAME: agent_type.get_qualified_class_name(),
            KeyConstants.ADDITIONAL_TOPICS: set(),
            KeyConstants.PROPERTIES: {},
            KeyConstants.LISTEN_TO_DEFAULT_TOPIC: True,
            KeyConstants.DEPENDENCY_MAP: {},
            KeyConstants.PREDICATES: {},
        }

        self.required_fields_set = {
            KeyConstants.NAME: False,
            KeyConstants.DESCRIPTION: False,
        }

    def set_id(self, agent_id: str) -> Self:
        """
        Set the ID for the Agent.
        """

        assert agent_id, "ID cannot be empty."
        self.agent_spec_dict[KeyConstants.ID] = agent_id
        return self

    def set_name(self, name: str) -> Self:
        """
        Set the name for the Agent.
        """

        assert name, "Name cannot be empty."
        assert len(name) <= 64, "Name cannot be longer than 64 characters."
        assert len(name) >= 1, "Name cannot be empty."

        self.agent_spec_dict[KeyConstants.NAME] = name
        self.required_fields_set[KeyConstants.NAME] = True
        return self

    def set_description(self, description: str) -> Self:
        """
        Set the description for the Agent.
        """

        assert description, "Description cannot be empty."
        assert len(description) >= 1, "Description cannot be empty."

        self.agent_spec_dict[KeyConstants.DESCRIPTION] = description
        self.required_fields_set[KeyConstants.DESCRIPTION] = True
        return self

    def add_additional_topic(self, topic: str) -> Self:
        """
        Add an additional topic for the Agent.
        """

        self.agent_spec_dict[KeyConstants.ADDITIONAL_TOPICS].add(topic)
        return self

    def set_properties(self, props: dict | APT) -> Self:
        """
        Set a property for the Agent.
        """
        if isinstance(props, dict) or (
            isclass(self.agent_props_type)
            and issubclass(self.agent_props_type, BaseAgentProps)
            and isinstance(props, self.agent_props_type)
        ):
            self.agent_spec_dict[KeyConstants.PROPERTIES] = props
        else:
            raise ValueError(f"Invalid properties type: {type(props)}")  # pragma: no cover
        return self

    def listen_to_default_topic(self, listen: bool) -> Self:
        """
        Configure whether to listen on default topic for the Agent.
        """
        self.agent_spec_dict[KeyConstants.LISTEN_TO_DEFAULT_TOPIC] = listen
        return self

    def validate(self) -> None:
        """
        Validate the AgentBuilder instance.
        """

        missing_fields = [field for field, set in self.required_fields_set.items() if not set]
        if missing_fields:
            raise ValueError(f"Missing required fields: {missing_fields}")

    def set_dependency_map(self, dependency_map: Dict[str, DependencySpec]) -> Self:
        """
        Set the dependency map for the Agent.
        """
        self.agent_spec_dict[KeyConstants.DEPENDENCY_MAP] = dependency_map
        return self

    def add_dependency_resolver(self, dep_key: str, dep_spec: DependencySpec) -> Self:
        """
        Add a dependency to the Agent.
        """
        self.agent_spec_dict[KeyConstants.DEPENDENCY_MAP][dep_key] = dep_spec
        return self

    def act_only_when_tagged(self, act_only_when_tagged: bool) -> Self:
        """
        Configure whether the agent should act only when tagged.
        """
        self.agent_spec_dict[KeyConstants.ACT_ONLY_WHEN_TAGGED] = act_only_when_tagged
        return self

    def add_predicate(self, method_name: str, predicate: RuntimePredicate) -> Self:
        """
        Add a predicate for the Agent.
        """
        self.agent_spec_dict[KeyConstants.PREDICATES][method_name] = predicate
        return self

    def build_spec(self) -> AgentSpec[APT]:
        """
        Build and return an AgentSpec instance with the set properties.
        """

        self.validate()
        dict_copy = self.agent_spec_dict.copy()
        dict_copy[KeyConstants.ADDITIONAL_TOPICS] = list(dict_copy[KeyConstants.ADDITIONAL_TOPICS])
        return AgentSpec[APT].model_validate(dict_copy)


class GuildBuilder:
    """
    Builder class for Guild.
    """

    def __init__(
        self,
        guild_id: Optional[str] = None,
        guild_name: Optional[str] = None,
        guild_description: Optional[str] = None,
    ):
        """
        Constructor for GuildBuilder
        Args:
            guild_id (Optional[str]): The ID of the guild. If not provided, a unique ID will be generated using shortuuid.
            guild_name (Optional[str]): The name of the guild.
            guild_description (Optional[str]): The description of the guild.
        """
        self.guild_spec_dict: dict = {
            KeyConstants.ID: guild_id if guild_id else shortuuid.uuid(),
            KeyConstants.NAME: guild_name,
            KeyConstants.DESCRIPTION: guild_description,
            KeyConstants.PROPERTIES: {},
            KeyConstants.AGENTS: [],
            KeyConstants.DEPENDENCY_MAP: {},
            KeyConstants.ROUTES: RoutingSlip(),
            KeyConstants.CONFIGURATION: {},
        }

        self.required_fields_set = {
            KeyConstants.NAME: guild_name is not None,
            KeyConstants.DESCRIPTION: guild_description is not None,
        }

    def set_name(self, name: str) -> "GuildBuilder":
        """
        Set the name for the Guild.

        Args:
            name (str): The name to set.

        Returns:
            GuildBuilder: The current GuildBuilder instance.
        """
        assert name, "Name cannot be empty."
        assert len(name) <= 64, "Name cannot be longer than 64 characters."
        assert len(name) >= 1, "Name cannot be empty."

        self.guild_spec_dict[KeyConstants.NAME] = name
        self.required_fields_set[KeyConstants.NAME] = True
        return self

    def set_description(self, description: str) -> "GuildBuilder":
        """
        Set the description for the Guild.

        Args:
            description (str): The description to set.

        Returns:
            GuildBuilder: The current GuildBuilder instance.
        """
        assert description, "Description cannot be empty."
        assert len(description) >= 1, "Description cannot be empty."

        self.guild_spec_dict[KeyConstants.DESCRIPTION] = description
        self.required_fields_set[KeyConstants.DESCRIPTION] = True
        return self

    def set_property(self, property_name: str, property_value: Any) -> "GuildBuilder":
        """
        Set a property for the Guild.

        Args:
            property_name (str): The name of the property to set.
            property_value (Any): The value of the property to set.

        Returns:
            GuildBuilder: The current GuildBuilder instance.
        """
        self.guild_spec_dict[KeyConstants.PROPERTIES][property_name] = property_value
        return self

    def set_execution_engine(self, execution_engine_clz: str) -> "GuildBuilder":
        """
        Set the execution engine for the Guild.

        Args:
            execution_engine_clz (str): The class name of the execution engine to set.

        Returns:
            GuildBuilder: The current GuildBuilder instance.
        """
        self.guild_spec_dict[KeyConstants.PROPERTIES][GSKC.EXECUTION_ENGINE] = execution_engine_clz
        return self

    def set_messaging(self, backend_module: str, backend_class: str, backend_config: dict) -> "GuildBuilder":
        """
        Set the messaging configuration for the Guild.

        Args:
            messaging (MessagingConfig): The messaging configuration to set.

        Returns:
            GuildBuilder: The current GuildBuilder instance.
        """
        self.guild_spec_dict[KeyConstants.PROPERTIES][GSKC.MESSAGING] = {
            GSKC.BACKEND_MODULE: backend_module,
            GSKC.BACKEND_CLASS: backend_class,
            GSKC.BACKEND_CONFIG: backend_config,
        }
        return self

    def set_dependency_map(self, dependency_map: Dict[str, DependencySpec]) -> "GuildBuilder":
        """
        Set the dependency map for the Agent.
        """
        self.guild_spec_dict[KeyConstants.DEPENDENCY_MAP] = dependency_map
        return self

    def add_dependency_resolver(self, dep_key: str, dep_spec: DependencySpec) -> "GuildBuilder":
        """
        Add a dependency to the Agent.
        """
        self.guild_spec_dict[KeyConstants.DEPENDENCY_MAP][dep_key] = dep_spec
        return self

    def load_dependency_map_from_yaml(self, filepath: str) -> "GuildBuilder":
        """
        Load the dependency map for the Agent.
        """
        dependency_map = GuildHelper.read_dependencies_config(filepath)
        self.guild_spec_dict[KeyConstants.DEPENDENCY_MAP] = dependency_map
        return self

    @classmethod
    def _from_spec_dict(cls, spec_dict: dict) -> "GuildBuilder":
        """
        Build a GuildBuilder instance from a dictionary specification.

        Args:
            spec_dict (dict): The dictionary specification to build from.

        Returns:
            GuildBuilder: The built GuildBuilder instance.
        """
        # Create a GuildBuilder instance with the parsed dictionary.
        builder = cls(
            guild_id=spec_dict.get(KeyConstants.ID),
            guild_name=spec_dict.get(KeyConstants.NAME),
            guild_description=spec_dict.get(KeyConstants.DESCRIPTION),
        )

        # Set the properties and agents from the parsed dictionary.
        builder.guild_spec_dict[KeyConstants.PROPERTIES] = spec_dict.get(KeyConstants.PROPERTIES, {})
        builder.guild_spec_dict[KeyConstants.DEPENDENCY_MAP] = spec_dict.get(KeyConstants.DEPENDENCY_MAP, {})
        configuration = spec_dict.get(KeyConstants.CONFIGURATION, {})

        if configuration:
            updated_agents = []
            updated_routes = []
            for agent_spec in spec_dict.get(KeyConstants.AGENTS, []):
                transformed_agent_json = chevron.render(json.dumps(agent_spec), configuration)
                agent_spec_with_config = AgentSpec.model_validate(json.loads(transformed_agent_json))
                updated_agents.append(agent_spec_with_config)
            routing_slip_dict = spec_dict.get(KeyConstants.ROUTES, {})
            if routing_slip_dict:
                for routing_rule in routing_slip_dict.get("steps"):
                    transformed_rule_json = chevron.render(json.dumps(routing_rule), configuration)
                    routing_rule_with_spec = RoutingRule.model_validate(json.loads(transformed_rule_json))
                    updated_routes.append(routing_rule_with_spec)

            builder.guild_spec_dict[KeyConstants.AGENTS] = updated_agents
            builder.guild_spec_dict[KeyConstants.ROUTES] = RoutingSlip(steps=updated_routes)
        else:
            builder.guild_spec_dict[KeyConstants.AGENTS] = spec_dict.get(KeyConstants.AGENTS, [])
            builder.guild_spec_dict[KeyConstants.ROUTES] = spec_dict.get(KeyConstants.ROUTES, RoutingSlip())
        return builder

    @classmethod
    def from_spec_yaml(cls, spec_yaml: str) -> "GuildBuilder":
        """
        Build a GuildBuilder instance from a YAML specification.

        Args:
            spec_yaml (str): The YAML specification to build from.

        Returns:
            GuildBuilder: The built GuildBuilder instance.
        """
        # Load the YAML spec, parse it and build the GuildBuilder instance.
        guild_spec_dict = yaml.safe_load(spec_yaml)

        return cls._from_spec_dict(guild_spec_dict)

    @classmethod
    def from_spec_json(cls, spec_json: str) -> "GuildBuilder":
        """
        Build a GuildBuilder instance from a JSON specification.

        Args:
            spec_json (str): The JSON specification to build from.

        Returns:
            GuildBuilder: The built GuildBuilder instance.
        """
        # Load the JSON spec, parse it and build the GuildBuilder instance.
        # Parse the JSON string into a dictionary.
        guild_spec_dict = json.loads(spec_json)

        return cls._from_spec_dict(guild_spec_dict)

    @classmethod
    def from_yaml_file(cls, file_path: str) -> "GuildBuilder":
        """
        Build a GuildBuilder instance from a YAML file.

        Args:
            file_path (str): The path to the YAML file.

        Returns:
            GuildBuilder: The built GuildBuilder instance.
        """
        # Load the YAML file, parse it and build the GuildBuilder instance.
        with open(file_path, "r") as file:
            return cls.from_spec_yaml(file.read())

    @classmethod
    def from_json_file(cls, file_path: str) -> "GuildBuilder":
        """
        Build a GuildBuilder instance from a JSON file.

        Args:
            file_path (str): The path to the JSON file.

        Returns:
            GuildBuilder: The built GuildBuilder instance.
        """
        # Load the JSON file, parse it and build the GuildBuilder instance.
        with open(file_path, "r") as file:
            return cls.from_spec_json(file.read())

    def add_agent_spec(self, agent: AgentSpec) -> "GuildBuilder":
        """
        Add a agent to the Guild.

        Args:
            agent (AgentSpec): The agent to add.

        Returns:
            GuildBuilder: The current GuildBuilder instance.
        """
        self.guild_spec_dict[KeyConstants.AGENTS].append(agent)
        return self

    def set_routes(self, routes: RoutingSlip) -> "GuildBuilder":
        """
        Set the routes for the Guild.

        Args:
            routes (RoutingSlip): The routes to set.

        Returns:
            GuildBuilder: The current GuildBuilder instance.
        """
        self.guild_spec_dict[KeyConstants.ROUTES] = routes
        return self

    def add_route(self, route: RoutingRule) -> "GuildBuilder":
        """
        Add a route to the Guild.

        Args:
            route (RoutingRule): The route to add.

        Returns:
            GuildBuilder: The current GuildBuilder instance.
        """
        routes: RoutingSlip = self.guild_spec_dict[KeyConstants.ROUTES]
        routes.add_step(route)
        return self

    def validate(self) -> None:
        """
        Validate the GuildBuilder instance.

        Raises:
            ValueError: If any required fields are missing.
        """
        missing_fields = [field for field, set in self.required_fields_set.items() if not set]
        if missing_fields:
            raise ValueError(f"Missing required fields: {missing_fields}")

    def build_spec(self) -> GuildSpec:
        """
        Build and return a GuildSpec instance with the set properties.

        Returns:
            GuildSpec: The built GuildSpec instance.
        """
        self.validate()
        return GuildSpec(**self.guild_spec_dict)

    @classmethod
    def from_spec(cls, guild_spec: GuildSpec) -> "GuildBuilder":
        """
        Build a GuildBuilder instance from a GuildSpec.

        Args:
            guild_spec (GuildSpec): The GuildSpec to build from.

        Returns:
            GuildBuilder: The built GuildBuilder instance.
        """

        if not guild_spec:
            raise ValueError("GuildSpec cannot be None.")

        builder = cls(
            guild_id=guild_spec.id,
            guild_name=guild_spec.name,
            guild_description=guild_spec.description,
        )

        builder.guild_spec_dict[KeyConstants.PROPERTIES] = guild_spec.properties
        builder.guild_spec_dict[KeyConstants.AGENTS] = guild_spec.agents
        builder.guild_spec_dict[KeyConstants.DEPENDENCY_MAP] = guild_spec.dependency_map
        builder.guild_spec_dict[KeyConstants.ROUTES] = guild_spec.routes

        return builder

    def launch(self, organization_id: str) -> Guild:
        """
        Build and return a Guild instance with the set properties.
        This will launch all the agents in the guild.
        This method is used to launch the guild with all the agents.
        Note: This can be used directly in development and testing, but should not be used in production.
        In production, use bootstrap().

        Returns:
            Guild: The built Guild instance.
        """
        logging.info("Launching Guild with agents...")
        guild_spec = self.build_spec()
        logging.info(f"Guild Spec: {guild_spec.model_dump()}")
        guild = GuildHelper.shallow_guild_from_spec(guild_spec, organization_id)
        logging.info(f"Launching agents in guild {guild.id}")

        for agent in guild_spec.agents:
            logging.info(f"Launching agent {agent.name} in guild {guild.id}")
            logging.info(f"Agent Spec: {agent.model_dump()}")
            guild.launch_agent(agent)
            logging.info(f"Agent {agent.name} launched")

        is_running = guild.is_guild_running()
        logging.info(f"Guild {guild.id} is running: {is_running}")

        return guild

    def load(self, organization_id: str) -> Guild:
        """
        Build and return a Guild instance with the set properties.
        This will not launch the agents in the guild, but just register them in the guild instance.
        This method is useful when you want to load the guild from a saved state.
        Note: This can be used directly in development and testing, but should not be used in production.
        In production, use bootstrap().

        Returns:
            Guild: The built Guild instance.
        """
        guild_spec = self.build_spec()
        guild = GuildHelper.shallow_guild_from_spec(guild_spec, organization_id)

        for agent in guild_spec.agents:
            guild.register_agent(agent)

        return guild

    def load_or_launch(self, organization_id: str, skip_agents: List[str] = []) -> Guild:
        """
        Build and return a Guild instance with the set properties.
        This WILL launch the agents in the guild if they are not already running, or just register them in the guild instance.
        This method is useful when you want to load the guild from a saved state and launch it.
        Note: This can be used directly in development and testing, but should not be used in production.
        In production, use bootstrap().

        Returns:
            Guild: The built Guild instance.
        """
        guild_spec = self.build_spec()
        guild = GuildHelper.shallow_guild_from_spec(guild_spec, organization_id)

        for agent in guild_spec.agents:
            if agent.id not in skip_agents:
                guild.register_or_launch_agent(agent)

        return guild

    def bootstrap(self, metastore_database_url: str, organization_id: str) -> Guild:
        """
        Build and return a Guild instance with the set properties.
        This method will not launch or register the agents in the guild.
        It will instead add a GuildManagerAgent to the Guild, which will be responsible for launching or registering agents.

        Returns:
            Guild: A shallow instance of the Guild without the configured Agents.
        """
        # Build the GuildSpec and create a Guild instance from it.
        guild_spec = self.build_spec()
        guild = GuildHelper.shallow_guild_from_spec(guild_spec, organization_id)

        # Add GuildManagerAgent to the Guild.
        # Using class name instead of class to avoid circular import

        agent_spec = AgentSpec(  # type: ignore
            id=GuildHelper.get_manager_agent_id(guild_spec.id),
            name=GuildHelper.get_manager_agent_name(guild_spec.id),
            description=f"Guild Manager Agent for {guild.name}",
            class_name="rustic_ai.core.agents.system.guild_manager_agent.GuildManagerAgent",
            properties={
                "guild_spec": guild_spec.model_dump(),
                "database_url": metastore_database_url,
                "organization_id": organization_id,
            },
            additional_topics=[
                GuildTopics.SYSTEM_TOPIC,
                HealthConstants.HEARTBEAT_TOPIC,
                GuildTopics.GUILD_STATUS_TOPIC,
            ],
            listen_to_default_topic=False,
        )

        try:
            guild.launch_agent(agent_spec)
            return guild
        except Exception as e:
            logging.error(f"Error launching GuildManagerAgent: {e}")
            raise e


class GuildHelper:
    """
    A class to help with guild creation.
    """

    @staticmethod
    def get_manager_agent_id(guild_id) -> str:
        return f"{guild_id}#manager_agent"

    @staticmethod
    def get_manager_agent_name(guild_id) -> str:
        return f"GuildManagerAgent4{guild_id}"

    @staticmethod
    def get_default_messaging_config() -> dict:
        """
        Get the default MessagingConfig.

        Returns:
            MessagingConfig: The default messaging configuration.
        """
        return {
            GSKC.BACKEND_MODULE: os.environ.get(
                EnvConstants.RUSTIC_AI_MESSAGING_MODULE,
                "rustic_ai.core.messaging.backend.embedded_backend",
            ),
            GSKC.BACKEND_CLASS: os.environ.get(EnvConstants.RUSTIC_AI_MESSAGING_CLASS, "EmbeddedMessagingBackend"),
            GSKC.BACKEND_CONFIG: json.loads(os.environ.get(EnvConstants.RUSTIC_AI_MESSAGING_BACKEND_CONFIG, "{}")),
        }

    @staticmethod
    def get_messaging_config(guild_spec: GuildSpec) -> MessagingConfig:
        """
        Get the MessagingConfig from the GuildSpec.

        Args:
            guild_spec: The GuildSpec to get the messaging configuration from.

        Returns:
            MessagingConfig: The messaging configuration.
        """
        messaging_config: dict = GuildHelper.get_default_messaging_config()

        if guild_spec.properties and GSKC.MESSAGING in guild_spec.properties:
            logging.debug(f"GuildSpec properties: {guild_spec.properties}")
            messaging_config = guild_spec.properties.get(GSKC.MESSAGING, {})
        else:
            logging.debug(f"Using default messaging config: {messaging_config}")

        return MessagingConfig.model_validate(messaging_config)

    @staticmethod
    def get_default_messaging_client() -> Type[Client]:
        """
        Get the default Messaging Client.

        Returns:
            Type[Client]: The default messaging client.
        """
        client_type: Type[Client] = MessageTrackingClient
        if os.environ.get(EnvConstants.RUSTIC_AI_CLIENT_TYPE):  # pragma: no cover
            client_type = class_utils.get_client_class(
                os.environ.get(EnvConstants.RUSTIC_AI_CLIENT_TYPE, MessageTrackingClient.get_qualified_class_name())
            )

        return client_type

    @staticmethod
    def get_messaging_client(guild_spec: GuildSpec) -> Type[Client]:
        """
        Get the Messaging Client from the GuildSpec.

        Args:
            guild_spec: The GuildSpec to get the messaging client from.

        Returns:
            Type[Client]: The messaging client.
        """
        client_type: Type[Client] = GuildHelper.get_default_messaging_client()

        if guild_spec.properties and "client_type" in guild_spec.properties:
            client_type_cname = guild_spec.properties.get("client_type")
            if client_type_cname:
                client_type = class_utils.get_client_class(client_type_cname)
            else:  # pragma: no cover
                client_type = MessageTrackingClient

        return client_type

    @staticmethod
    def get_messaging_client_properties(guild_spec: GuildSpec) -> dict:
        """
        Get the Messaging Client properties from the GuildSpec.

        Args:
            guild_spec: The GuildSpec to get the messaging client properties from.

        Returns:
            dict: The messaging client properties.
        """
        client_properties: dict = {}
        if guild_spec.properties and "client_properties" in guild_spec.properties:
            client_properties = guild_spec.properties.get("client_properties", {})
        elif os.environ.get(EnvConstants.RUSTIC_AI_CLIENT_PROPERTIES):
            client_properties = json.loads(os.environ.get(EnvConstants.RUSTIC_AI_CLIENT_PROPERTIES, "{}"))

        return client_properties

    @staticmethod
    def get_default_execution_engine() -> str:
        """
        Get the default Execution Engine.

        Returns:
            str: The default execution engine.
        """
        return os.environ.get(EnvConstants.RUSTIC_AI_EXECUTION_ENGINE, SyncExecutionEngine.get_qualified_class_name())

    @staticmethod
    def get_execution_engine(guild_spec: GuildSpec) -> str:
        """
        Get the Execution Engine from the GuildSpec.

        Args:
            guild_spec: The GuildSpec to get the execution engine from.

        Returns:
            str: The execution engine.
        """
        execution_engine_clz = GuildHelper.get_default_execution_engine()
        if guild_spec.properties and GSKC.EXECUTION_ENGINE in guild_spec.properties:
            execution_engine_clz = guild_spec.properties.get(GSKC.EXECUTION_ENGINE, "")

        return execution_engine_clz

    @staticmethod
    def get_guild_dependency_map(guild_spec: GuildSpec) -> Dict[str, DependencySpec]:
        """
        Get the Guild Dependency Map.

        Returns:
            dict: The Guild Dependency Map.
        """
        dependency_cfg_file = os.environ.get(EnvConstants.RUSTIC_AI_DEPENDENCY_CONFIG, "conf/agent-dependencies.yaml")
        config_deps_map = GuildHelper.read_dependencies_config(dependency_cfg_file)
        guild_exec_map = guild_spec.dependency_map

        return {**config_deps_map, **guild_exec_map}

    @staticmethod
    def read_dependencies_config(filepath: str) -> Dict[str, DependencySpec]:
        """
        Read the dependencies configuration from yaml.

        Returns:
            dict: The dependencies configuration.
        """
        if not os.path.exists(filepath):  # pragma: no cover
            logging.warning("Dependencies configuration file not found.")
            return {}

        deps_config = {}
        with open(filepath) as depsfile:
            deps_config = yaml.safe_load(depsfile)

        deps = {k: DependencySpec.model_validate(v) for k, v in deps_config.items()}

        return deps

    @staticmethod
    def shallow_guild_from_spec(guild_spec: GuildSpec, organization_id: str) -> Guild:
        """
        Builds a Shallow (without the agents) Guild from a GuildSpec.

        Args:
            guild_spec: The specification to build from.
            organization_id: The organization running the guild

        Returns:
            The built Guild instance.
        """

        messaging_config: MessagingConfig = GuildHelper.get_messaging_config(guild_spec)

        client_type: type[Client] = GuildHelper.get_messaging_client(guild_spec)

        client_properties: dict = GuildHelper.get_messaging_client_properties(guild_spec)

        execution_engine_clz: str = GuildHelper.get_execution_engine(guild_spec)

        dependency_map = GuildHelper.get_guild_dependency_map(guild_spec)

        guild = Guild(
            id=guild_spec.id,
            name=guild_spec.name,
            description=guild_spec.description,
            execution_engine_clz=execution_engine_clz,
            messaging_config=messaging_config,
            client_type=client_type,
            client_properties=client_properties,
            dependency_map=dependency_map,
            routes=guild_spec.routes,
            organization_id=organization_id,
        )

        return guild

    @staticmethod
    def get_default_state_mgr_config() -> dict:
        """
        Get the default StateManagerConfig.

        Returns:
            dict: The default StateManager configuration.
        """
        return json.loads(os.environ.get(EnvConstants.RUSTIC_AI_STATE_MANAGER_CONFIG, "{}"))

    @staticmethod
    def get_state_mgr_config(guild_spec: GuildSpec) -> dict:
        """
        Get the MessagingConfig from the GuildSpec.

        Args:
            guild_spec: The GuildSpec to get the messaging configuration from.

        Returns:
            dict: The state manager configuration.
        """
        state_manager_config: dict = GuildHelper.get_default_state_mgr_config()

        if guild_spec.properties and GSKC.STATE_MANAGER_CONFIG in guild_spec.properties:
            logging.debug(f"GuildSpec properties: {guild_spec.properties}")
            state_manager_config = guild_spec.properties.get(GSKC.STATE_MANAGER_CONFIG, {})
        else:
            logging.debug(f"Using default state manager config: {state_manager_config}")

        return state_manager_config

    @staticmethod
    def get_default_state_manager() -> str:
        """
        Get the default State Manager.

        Returns:
            str: The default state manager.
        """
        return os.environ.get(EnvConstants.RUSTIC_AI_STATE_MANAGER, InMemoryStateManager.get_qualified_class_name())

    @staticmethod
    def get_state_manager(guild_spec: GuildSpec) -> str:
        """
        Get the State Manager from the GuildSpec.

        Args:
            guild_spec: The GuildSpec to get the state manager from.

        Returns:
            str: The state manager for the guild.
        """
        state_manager_clz = GuildHelper.get_default_state_manager()
        if guild_spec.properties and GSKC.STATE_MANAGER in guild_spec.properties:
            state_manager_clz = guild_spec.properties.get(GSKC.STATE_MANAGER, "")

        return state_manager_clz


class RouteBuilder:

    def __init__(self, from_agent: Union[Type[Agent], AgentTag, AgentSpec]):
        self.rule_dict: dict = {}

        if isinstance(from_agent, AgentSpec):
            self.rule_dict[RoutingKeys.AGENT.value] = AgentTag(name=from_agent.name)
        elif isinstance(from_agent, AgentTag):
            self.rule_dict[RoutingKeys.AGENT.value] = from_agent
        elif isclass(from_agent) and issubclass(from_agent, Agent):
            self.rule_dict[RoutingKeys.AGENT_TYPE.value] = from_agent.get_qualified_class_name()
        else:
            raise ValueError("Invalid from_agent type")

    def from_method(self, method_name: Union[Callable, str]) -> "RouteBuilder":
        self.rule_dict[RoutingKeys.METHOD_NAME.value] = method_name.__name__ if callable(method_name) else method_name
        return self

    def on_message_format(self, message_format: Union[Type[BaseModel], str]) -> "RouteBuilder":
        self.rule_dict[RoutingKeys.MESSAGE_FORMAT.value] = (
            message_format if isinstance(message_format, str) else get_qualified_class_name(message_format)
        )
        return self

    def filter_on_origin(
        self,
        origin_sender: Optional[Union[AgentTag, AgentSpec]] = None,
        origin_topic: Optional[str] = None,
        origin_message_format: Optional[str] = None,
    ) -> "RouteBuilder":
        self.rule_dict[RoutingKeys.ORIGIN_FILTER.value] = {}

        if origin_sender:
            self.rule_dict[RoutingKeys.ORIGIN_FILTER.value][OriginFilterKeys.ORIGIN_SENDER.value] = (
                origin_sender if isinstance(origin_sender, AgentTag) else AgentTag(name=origin_sender.name)
            )

        if origin_topic:
            self.rule_dict[RoutingKeys.ORIGIN_FILTER.value][OriginFilterKeys.ORIGIN_TOPIC.value] = origin_topic

        if origin_message_format:
            self.rule_dict[RoutingKeys.ORIGIN_FILTER.value][
                OriginFilterKeys.ORIGIN_MESSAGE_FORMAT.value
            ] = origin_message_format

        return self

    def set_destination_topics(self, destination_topics: str | List[str]) -> "RouteBuilder":
        if RoutingKeys.DESTINATION.value not in self.rule_dict:
            self.rule_dict[RoutingKeys.DESTINATION.value] = {}

        self.rule_dict[RoutingKeys.DESTINATION.value][DestinationKeys.TOPICS.value] = destination_topics

        return self

    def add_recipients(self, recipients: List[Union[AgentTag, AgentSpec]]) -> "RouteBuilder":
        if RoutingKeys.DESTINATION.value not in self.rule_dict:
            self.rule_dict[RoutingKeys.DESTINATION.value] = {}

        if DestinationKeys.RECIPIENT_LIST.value not in self.rule_dict[RoutingKeys.DESTINATION.value]:
            self.rule_dict[RoutingKeys.DESTINATION.value][DestinationKeys.RECIPIENT_LIST.value] = []

        rlist = [
            recipient if isinstance(recipient, AgentTag) else AgentTag(name=recipient.name) for recipient in recipients
        ]

        self.rule_dict[RoutingKeys.DESTINATION.value][DestinationKeys.RECIPIENT_LIST.value].extend(rlist)

        return self

    def mark_forwarded(self, mark_forwarded: bool) -> "RouteBuilder":
        self.rule_dict[RoutingKeys.MARK_FORWARDED.value] = mark_forwarded
        return self

    def set_route_times(self, route_times: int) -> "RouteBuilder":
        self.rule_dict[RoutingKeys.ROUTE_TIMES.value] = route_times
        return self

    def set_payload_transformer(
        self, output_type: Type[BaseModel], payload_xform: Union[JxScript, str]
    ) -> "RouteBuilder":
        if RoutingKeys.TRANSFORMER.value in self.rule_dict:
            raise ValueError("Transformer can only be set once.")

        self.rule_dict[RoutingKeys.TRANSFORMER.value] = PayloadTransformer(
            style=TransformationType.SIMPLE,
            output_format=get_qualified_class_name(output_type),
            expression=payload_xform.serialize() if isinstance(payload_xform, JxScript) else payload_xform,
        )
        return self

    def set_functional_transformer(self, functional_xform: Union[JxScript, str]) -> "RouteBuilder":
        if RoutingKeys.TRANSFORMER.value in self.rule_dict:
            raise ValueError("Transformer can only be set once.")

        self.rule_dict[RoutingKeys.TRANSFORMER.value] = FunctionalTransformer(
            style=TransformationType.CBR,
            handler=functional_xform.serialize() if isinstance(functional_xform, JxScript) else functional_xform,
        )
        return self

    def set_agent_state_update(
        self,
        update_agent_state: Union[JxScript, str],
        update_format: StateUpdateFormat = StateUpdateFormat.JSON_MERGE_PATCH,
    ) -> "RouteBuilder":
        state_transformer = StateTransformer(
            update_format=update_format,
            state_update=(
                update_agent_state.serialize() if isinstance(update_agent_state, JxScript) else update_agent_state
            ),
        )
        self.rule_dict[StateUpdateActions.AGENT_STATE_UPDATE.value] = state_transformer
        return self

    def set_guild_state_update(
        self,
        update_guild_state: Union[JxScript, str],
        update_format: StateUpdateFormat = StateUpdateFormat.JSON_MERGE_PATCH,
    ) -> "RouteBuilder":
        state_transformer = StateTransformer(
            update_format=update_format,
            state_update=(
                update_guild_state.serialize() if isinstance(update_guild_state, JxScript) else update_guild_state
            ),
        )
        self.rule_dict[StateUpdateActions.GUILD_STATE_UPDATE.value] = state_transformer
        return self

    def set_process_status(self, process_status: ProcessStatus) -> "RouteBuilder":
        self.rule_dict[RoutingKeys.PROCESS_STATUS.value] = process_status
        return self

    def set_reason(self, reason: str) -> "RouteBuilder":
        self.rule_dict[RoutingKeys.REASON.value] = reason
        return self

    def build(self) -> RoutingRule:
        return RoutingRule.model_validate(self.rule_dict)
