from abc import ABC, abstractmethod
from typing import (
    Annotated,
    Any,
    Dict,
    Generic,
    List,
    Literal,
    Optional,
    Set,
    Type,
    TypeVar,
    Union,
    cast,
)

import jsonata
from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag, model_validator
import shortuuid

from rustic_ai.core.guild.agent_ext.depends.dependency_resolver import DependencySpec
from rustic_ai.core.guild.metaprog.constants import MetaclassConstants
from rustic_ai.core.messaging.core.message import AgentTag, RoutingSlip
from rustic_ai.core.utils.basic_class_utils import get_class_from_name
from rustic_ai.core.utils.json_utils import JsonDict


class BaseAgentProps(BaseModel):
    """
    Empty class for Agent properties.
    """

    @classmethod
    def get_qualified_class_name(cls) -> str:
        return f"{cls.__module__}.{cls.__name__}"


APT = TypeVar("APT", bound=BaseAgentProps)


class KeyConstants:
    """
    Constants for keys used in GuildSpec properties.
    """

    EXECUTION_ENGINE = "execution_engine"
    MESSAGING = "messaging"
    BACKEND_MODULE = "backend_module"
    BACKEND_CLASS = "backend_class"
    BACKEND_CONFIG = "backend_config"
    CLIENT_TYPE = "client_type"
    CLIENT_PROPERTIES = "client_properties"
    STATE_MANAGER = "state_manager"
    STATE_MANAGER_CONFIG = "state_manager_config"


class GuildTopics:
    """
    Constants for global values.
    """

    DEFAULT_TOPICS: List[str] = ["default_topic"]

    SYSTEM_TOPIC: str = "system_topic"

    STATE_TOPIC: str = "state_topic"

    GUILD_STATUS_TOPIC: str = "guild_status_topic"

    ESSENTIAL_TOPICS: List[str] = [GUILD_STATUS_TOPIC, STATE_TOPIC]

    AGENT_SELF_INBOX_PREFIX: str = "agent_self_inbox"

    AGENT_INBOX_PREFIX: str = "agent_inbox"

    DEAD_LETTER_QUEUE: str = "dead_letter_queue"

    ERROR_TOPIC: str = "error_topic"

    @staticmethod
    def get_self_agent_inbox(agent_id: str) -> str:
        """
        Returns the inbox topic for the guild.
        """
        return f"{GuildTopics.AGENT_SELF_INBOX_PREFIX}:{agent_id}"

    @staticmethod
    def get_agent_inbox(agent_id: str) -> str:
        """
        Returns the inbox topic for the agent.
        """
        return f"{GuildTopics.AGENT_INBOX_PREFIX}:{agent_id}"


class RuntimePredicate(ABC, BaseModel):
    predicate_type: str

    @abstractmethod
    def evaluate(self, message: JsonDict, agent_state: JsonDict, guild_state: JsonDict) -> bool:
        pass


class JSONataPredicate(RuntimePredicate):
    predicate_type: Literal["jsonata_fn"] = "jsonata_fn"
    expression: str

    def evaluate(self, message: JsonDict, agent_state: JsonDict, guild_state: JsonDict) -> bool:
        expr = jsonata.Jsonata(self.expression)
        result = expr.evaluate({"message": message, "agent_state": agent_state, "guild_state": guild_state})

        # Make sure we return a boolean
        if result:
            return True
        else:
            return False


class TypeEqualsPredicate(RuntimePredicate):
    predicate_type: Literal["type_equals"] = "type_equals"
    expected_type: str

    def evaluate(self, message: JsonDict, agent_state: JsonDict, guild_state: JsonDict) -> bool:
        actual_type = message.get("type")
        return actual_type == self.expected_type


def predicate_type_discriminator(value: Any) -> str:
    if isinstance(value, dict):
        if "predicate_type" in value:
            return value["predicate_type"]
        else:
            return "jsonata_fn"
    return getattr(value, "predicate_type", "jsonata_fn")


RuntimePredicateType = Annotated[
    Union[
        Annotated[JSONataPredicate, Tag("jsonata_fn")],
        Annotated[TypeEqualsPredicate, Tag("type_equals")],
    ],
    Field(discriminator=Discriminator(predicate_type_discriminator)),
]


class ResourceSpec(BaseModel):
    """
    A specification for the resources required by an agent.

    Attributes:
        num_cpus (Optional[int | float]): The number of CPUs required by the agent.
        num_gpus (Optional[int | float]): The number of GPUs required by the agent.
        custom_resources (Optional[Dict[str, int | float]]): A dictionary of custom resources required by the agent.
    """

    num_cpus: Optional[int | float] = Field(default=None)
    num_gpus: Optional[int | float] = Field(default=None)
    custom_resources: Dict[str, int | float] = Field(default_factory=dict)


class QOSSpec(BaseModel):
    """
    A specification for the Quality of Service (QoS) settings for an agent.

    Attributes:
        timeout (Optional[int]): The timeout for the agent's operations in seconds.
        retry_count (Optional[int]): The number of retries for the agent's operations.
        latency (Optional[int]): The maximum acceptable latency for the agent's operations in milliseconds.
    """

    timeout: Optional[int] = None
    retry_count: Optional[int] = None
    latency: Optional[int] = None


class AgentSpec(BaseModel, Generic[APT]):
    """
    A specification for an agent that describes its name, description, and properties.

    Attributes:
        name (str): The name of the agent.
        description (str): A description of the agent.
        class_name (str): The name of the class of the agent.
        additional_topics (List[str]): A list of additional topics to which the agent should subscribe.
        properties (APT): The properties of the agent.
        listen_to_default_topic (bool): Whether the agent should listen to the default topic.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(default_factory=shortuuid.uuid)
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1)
    class_name: str
    additional_topics: List[str] = []
    properties: APT = Field(default_factory=lambda: BaseAgentProps())  # type: ignore
    listen_to_default_topic: bool = True

    act_only_when_tagged: bool = False

    predicates: Dict[str, RuntimePredicateType] = Field(
        default_factory=dict,
        description="A mapping of functions to their runtime predicates.",
    )

    # A mapping for guild's dependency to resolver class
    dependency_map: Dict[str, DependencySpec] = {}

    # Resource configuration for the agent useful for execution engines that support it
    resources: ResourceSpec = Field(default_factory=ResourceSpec)

    # Quality of Service (QoS) settings for the agent
    qos: QOSSpec = Field(default_factory=QOSSpec)

    _subscribed_topics: Set[str] = set()

    @property
    def props(self) -> APT:
        assert self.properties is not None, f"Agent type {self.class_name} does not have properties defined."
        return self.properties

    @property
    def subscribed_topics(self) -> Set[str]:
        if not self._subscribed_topics:
            topics: Set[str] = set(self.additional_topics)
            if self.listen_to_default_topic:
                topics.update(set(GuildTopics.DEFAULT_TOPICS))

            topics.add(GuildTopics.get_self_agent_inbox(self.id))
            topics.add(GuildTopics.get_agent_inbox(self.id))

            topics.update(set(GuildTopics.ESSENTIAL_TOPICS))
            self._subscribed_topics = topics
        return self._subscribed_topics

    @model_validator(mode="before")
    @classmethod
    def pre_build_validator(cls, data):

        class_name = data.get("class_name")
        agent_class: Type

        if not class_name:
            raise ValueError("class_name is required")
        else:
            try:
                agent_class = get_class_from_name(class_name)

                # Loading the class from the string to avoid circular imports

                agent_base_class = get_class_from_name("rustic_ai.core.guild.Agent")
            except Exception as e:
                raise ValueError(f"Invalid class name: {class_name}") from e

            if not issubclass(agent_class, agent_base_class):
                raise ValueError(f"Class {class_name} is not a subclass of Agent")

        properties_type: Type[BaseAgentProps] = agent_class.__annotations__[MetaclassConstants.AGENT_PROPS_TYPE] or BaseAgentProps  # type: ignore

        properties = data.get("properties")

        if properties_type != BaseAgentProps:
            if not properties or type(properties) is BaseAgentProps:
                data["properties"] = properties_type()
            elif properties and isinstance(properties, dict):
                data["properties"] = properties_type.model_validate(properties)
            elif not isinstance(properties, properties_type):
                raise ValueError(f"Properties must be an instance of {properties_type}")
        elif properties and type(properties) is not BaseAgentProps:
            raise ValueError(f"Agent {class_name} does not accept properties")

        return data

    @classmethod
    def get_pydantic_generic_type(cls) -> Type[BaseAgentProps]:
        margs = cls.__pydantic_generic_metadata__["args"]
        if len(margs) >= 1:
            gt = margs[0]
        else:
            gt = BaseAgentProps
        return cast(Type[BaseAgentProps], gt)


class GuildSpec(BaseModel):
    """
    A specification for a guild that describes its name, description, and agents.

    Attributes:
        name (str): The name of the guild.
        description (str): A description of the guild.
        properties (Dict[str, Any]): The properties of the guild.
        agents (list[AgentSpec]): A list of agents in the guild.
        dependency_map (Dict[str, DependencySpec]): A mapping for guild's dependency to resolver class.
        routes (RoutingSlip): The routes to be attached to every message coming in the guild.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(default_factory=shortuuid.uuid)
    name: Annotated[str, Field(min_length=1, max_length=64)]
    description: Annotated[str, Field(min_length=1)]
    properties: Dict[str, Any] = {}
    agents: list[AgentSpec] = []

    # A mapping for guild's dependency to resolver class
    dependency_map: Dict[str, DependencySpec] = {}

    routes: RoutingSlip = Field(default_factory=RoutingSlip)

    def __init__(self, **data):
        super().__init__(**data)

    def add_agent_spec(self, agent: AgentSpec):
        if agent not in self.agents:
            self.agents.append(agent)
        else:
            raise ValueError(f"Agent {agent.name} already exists in guild")

    def set_execution_engine(self, execution_engine: str):
        self.properties[KeyConstants.EXECUTION_ENGINE] = execution_engine

    def set_messaging(self, backend_module: str, backend_class: str, backend_config: dict = {}):
        self.properties[KeyConstants.MESSAGING] = {}

        self.properties[KeyConstants.MESSAGING][KeyConstants.BACKEND_MODULE] = backend_module
        self.properties[KeyConstants.MESSAGING][KeyConstants.BACKEND_CLASS] = backend_class
        self.properties[KeyConstants.MESSAGING][KeyConstants.BACKEND_CONFIG] = backend_config

    def get_execution_engine(self) -> Optional[str]:
        return self.properties.get("execution_engine", None)  # pragma: no cover

    def get_messaging(self) -> Optional[dict]:
        return self.properties.get(KeyConstants.MESSAGING, None)  # pragma: no cover

    def get_guild_agents(self) -> List[AgentTag]:
        return [AgentTag(id=agent.id, name=agent.name) for agent in self.agents]
