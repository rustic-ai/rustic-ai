import json
import logging
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Annotated, Any, Dict, List, Literal, Optional, TypeVar, Union

from jsonata import Jsonata
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_serializer,
    model_validator,
)

from rustic_ai.core.state.models import StateUpdateFormat
from rustic_ai.core.utils import GemstoneID, JsonDict, Priority

MDT = TypeVar("MDT", bound=Union[BaseModel, JsonDict])


class MessageConstants(StrEnum):
    RAW_JSON_FORMAT = "generic_json"


class AgentTag(BaseModel):
    """
    Represents a tag that can be assigned to an agent.

    Attributes:
        name (str): The name of the agent.
        id (str): The id of the agent.
    """

    id: Annotated[Optional[str], Field(default=None)] = None
    name: Annotated[Optional[str], Field(default=None)] = None

    def __str__(self):
        return f"[{self.name}]({self.id})"  # pragma: no cover

    def strict_equals(self, other: "AgentTag") -> bool:
        """
        Check if the agent tag is strictly equal to another agent tag.
        """
        return self.id == other.id and self.name == other.name  # pragma: no cover

    def __eq__(self, other: Any) -> bool:  # pragma: no cover
        if not isinstance(other, AgentTag):
            return False

        if self.id and self.id != other.id:
            return False

        if self.name and self.name != other.name:
            return False

        return True


class ProcessEntry(BaseModel):
    """
    Represents an entry for agent and previous message in the message history.

    Attributes:
        agent (AgentTag): Identifier or name of the agent.
        origin (int): ID of the previous message.
        result (int): ID of the current message.
    """

    agent: AgentTag
    origin: int
    result: int


class TransformationType(StrEnum):
    """
    Represents the type of transformer to apply to a message.
    """

    SIMPLE = "simple"
    CBR = "content_based_router"


class Transformer(BaseModel, ABC):
    """
    Represents a transformer to be applied to a message.

    Attributes:
        expression (str): The transformer to be applied to the message. This is a JSONata expression.
        output_format (str): The format of the transformed message.
    """

    model_config = ConfigDict(use_enum_values=True, validate_default=True)

    style: Literal[TransformationType.SIMPLE, TransformationType.CBR] = Field(default=TransformationType.SIMPLE)

    @abstractmethod
    def transform(
        self, origin: "Message", agent_state: JsonDict, guild_state: JsonDict, routable: "MessageRoutable"
    ) -> Optional["MessageRoutable"]:
        """
        Apply the transformer to a data.

        Args:
            origin (Message): The original message.
            routable (MessageRoutable): The routable message.

        Returns:
            Optional[MessageRoutable]:
                The transformed message content. If None, the transformer didn't work and the message should not be published.
        """
        pass


class PayloadTransformer(Transformer):

    output_format: Optional[str] = Field(default=MessageConstants.RAW_JSON_FORMAT)
    expression: Optional[str] = Field(default=None)

    def transform(
        self, origin: "Message", agent_state: JsonDict, guild_state: JsonDict, routable: "MessageRoutable"
    ) -> Optional["MessageRoutable"]:
        """
        A simple transformer that applies a JSONata expression to the message payload.
        This transformer is basic and acts only on the payload.
        """
        data = routable.payload

        try:
            if self.expression:
                expr = Jsonata(self.expression)
                evaluated = expr.evaluate(data)
                if evaluated is None:
                    return None
                routable.payload = evaluated

            if self.output_format:
                routable.format = self.output_format

        except Exception as e:
            logging.error(f"Error in transformer: {e}")
            return None

        return routable


class FunctionalTransformer(Transformer):

    handler: str

    def transform(
        self, origin: "Message", agent_state: JsonDict, guild_state: JsonDict, routable: "MessageRoutable"
    ) -> Optional["MessageRoutable"]:
        """
        A content-based router transformer that applies a JSONata expression to the message payload.
        This transformer is more complex and can act on the payload, topic, and other message fields.
        """

        try:
            if self.handler:
                expr = Jsonata(self.handler)
                current_dict = routable.model_dump()
                input = {
                    "origin": origin.model_dump(
                        include={"id", "sender", "topic", "recipient_list", "payload", "format"}
                    ),
                    "agent_state": agent_state,
                    "guild_state": guild_state,
                } | current_dict

                transformed = expr.evaluate(input)
                if transformed is None:
                    return None

                routable = MessageRoutable.model_validate(current_dict | transformed)
            else:
                return None
        except Exception as e:
            logging.error(f"Error in transformer: {e}")
            return None

        return routable


class StateUpdate(BaseModel):

    update_format: StateUpdateFormat = Field(
        default=StateUpdateFormat.JSON_MERGE_PATCH,
        description="""The format of the state update. Currently we support JSON Patch (https://datatracker.ietf.org/doc/html/rfc6902)
        and JSON Merge Patch (https://datatracker.ietf.org/doc/html/rfc7386) is supported.""",
    )

    state_update: JsonDict = Field(
        description="The update payload. The structure of the payload is defined by the update format.",
    )


class StateTransformer(BaseModel):
    """
    Represents a transformer to be applied to the state of an agent or guild.

    Attributes:
        expression (str): The transformer to be applied to the state. This is a JSONata expression.
        output_format (str): The format of the transformed state.
    """

    update_format: StateUpdateFormat = Field(default=StateUpdateFormat.JSON_MERGE_PATCH)
    state_update: Optional[str] = Field(default=None)

    def transform(
        self,
        origin: "Message",
        agent_state: JsonDict,
        guild_state: JsonDict,
        routed: "MessageRoutable",
        untransformed: "MessageRoutable",
    ) -> Optional[StateUpdate]:
        """
        Apply the transformer to the state of an agent or guild.
        """
        try:
            if self.state_update:
                expr = Jsonata(self.state_update)
                current_dict = routed.model_dump()
                input = {
                    "origin": origin.model_dump(
                        include={"id", "sender", "topic", "recipient_list", "payload", "format"}
                    ),
                    "agent_state": agent_state,
                    "guild_state": guild_state,
                    "untransformed": untransformed.model_dump(),
                } | current_dict

                transformed = expr.evaluate(input)
                if transformed is None:
                    return None
                else:
                    return StateUpdate(update_format=self.update_format, state_update=transformed)

            else:
                return None
        except Exception as e:
            logging.error(f"Error in transformer: {e}")
            return None


class RoutingOrigin(BaseModel):
    """
    Represents a filter for a message that triggered the current step in a routing slip.

    Attributes:
        origin_sender (Optional[AgentTag]): The agent that sent the message that triggered the current step.
        origin_topic (Optional[str]): The topic where the original message was sent.
        origin_message_format (Optional[str]): The format of the original message.
    """

    origin_sender: Optional[AgentTag] = None
    origin_topic: Optional[str] = None
    origin_message_format: Optional[str] = None

    def matches(self, sender: AgentTag, topics: Union[str, List[str]], message_format: str) -> bool:
        """
        Check if the filter matches the source, topic, and message format.

        Args:
            source (AgentTag): The source agent.
            topic (Union[str, List[str]]): The topic of the message.
            message_format (str): The format of the message.

        Returns:
            bool: True if the filter matches, False otherwise.
        """
        if self.origin_sender:  # pragma: no cover
            if self.origin_sender and self.origin_sender != sender:
                return False

        if self.origin_topic:
            if isinstance(topics, str) and self.origin_topic != topics:
                return False
            elif isinstance(topics, list) and self.origin_topic not in topics:
                return False

        if self.origin_message_format and self.origin_message_format != message_format:
            return False
        return True


class RoutingDestination(BaseModel):
    """
    Represents a destination for a message in a routing slip.

    Attributes:
        topics (Optional[Union[str, List[str]]]): The topic to send the message to be processed, if not specified, it will be same as the
            incoming message with a fallback to default_topic.
        recipient_list (List[AgentTag]): List of agents to tag for this step, be default it will not tag any agents.
        priority (Optional[Priority]): The priority of the message produced .
    """

    topics: Optional[Union[str, List[str]]] = None
    recipient_list: List[AgentTag] = []
    priority: Optional[Priority] = None


class RoutingRule(BaseModel):
    """
    Represents an entry in a routing slip.

    Attributes:
        agent (Optional[AgentTag]): The agent which is sending this message. Either this or agent_type must be provided.
        agent_type (Optional[str]): The type of the agent sending the message. Either this or agent must be provided.
        method_name (Optional[str]): The method in the agent from which the message is sent.
        origin_filter (Optional[RoutingOrigin]): Apply the step if the origin message that triggered the process matches the filter.
        message_format (Optional[str]): The format of the message being sent that this step will act on.
        destination (Optional[RoutingDestination]): The destination for the message.
        mark_forwarded (Optional[bool]): Mark the message as forwarded.
        route_times (Optional[int]): The number of times to route the message. If -1, it will route everytime the rule is satified. Default is 1.
        transformer (Optional[Transformation]): The transformer to be applied to the message.
        agent_state_update (Optional[StateTransformer]): The state update request to be applied to the agent.
        guild_state_update (Optional[StateTransformer]): The state update request to be applied to the guild.
    """

    agent: Optional[AgentTag] = None
    agent_type: Optional[str] = None
    method_name: Optional[str] = None
    origin_filter: Optional[RoutingOrigin] = None
    message_format: Optional[str] = None
    destination: Optional[RoutingDestination] = None
    mark_forwarded: Optional[bool] = Field(default=False)
    route_times: Optional[int] = Field(default=1)

    transformer: Optional[Union[PayloadTransformer, FunctionalTransformer]] = None

    agent_state_update: Optional[StateTransformer] = None
    guild_state_update: Optional[StateTransformer] = None

    @model_validator(mode="before")
    @classmethod
    def pre_validate_rule(cls, data):
        """
        Ensure at least one of agent or agent_type is provided.
        """
        if not data.get("agent") and not data.get("agent_type"):
            raise ValueError("Either agent or agent_type must be provided for a routing rule.")

        return data

    def decrement_route_times(self):
        """
        Decrement the route times for the step.
        """
        if self.route_times:
            self.route_times -= 1

    def is_done(self) -> bool:
        """
        Check if the step is done.

        Returns:
            bool: True if the step is done, False otherwise.
        """
        return self.route_times == 0

    def is_applicable(
        self,
        agent: AgentTag,
        agent_type: str,
        method_name: str,
        origin: RoutingOrigin,
        message_format: str,
    ) -> bool:
        """
        Check if the step is applicable for a message.

        Args:
            agent (AgentTag): The agent sending the message.
            agent_type (str): The type of the agent sending the message.
            method_name (str): The method in the agent from which the message is being sent.
            origin (RoutingOriginFilter): The origin message that triggered this process.
            message_format (str): The format of the message being sent.

        Returns:
            bool: True if the step is applicable, False otherwise.
        """

        if self.agent and self.agent != agent:
            return False  # pragma: no cover

        if self.agent_type and self.agent_type != agent_type:
            return False  # pragma: no cover

        if self.method_name and self.method_name != method_name:
            return False  # pragma: no cover

        assert origin is not None
        assert origin.origin_sender is not None
        assert origin.origin_topic is not None
        assert origin.origin_message_format is not None

        if self.origin_filter and not self.origin_filter.matches(
            origin.origin_sender, origin.origin_topic, origin.origin_message_format
        ):
            return False  # pragma: no cover

        if self.message_format and self.message_format != message_format:
            return False  # pragma: no cover

        return True

    def apply(
        self,
        origin: "Message",
        agent_state: JsonDict,
        guild_state: JsonDict,
        routable: "MessageRoutable",
        forwarding: bool,
    ) -> Optional["MessageRoutable"]:
        """
        Apply the step to a message.

        Args:
            message (Message): The message to apply the step to.

        Returns:
            Message: The message after applying the step.
        """

        routing_destination: RoutingDestination = self.destination or RoutingDestination()

        if routing_destination.topics:
            routable.topics = routing_destination.topics

        if routing_destination.priority:
            routable.priority = routing_destination.priority

        if routing_destination.recipient_list:
            routable.recipient_list = routing_destination.recipient_list

        if forwarding or self.mark_forwarded:
            # Use the original messages forwarding header if it exists or create a new one
            routable.forward_header = origin.forward_header or ForwardHeader(
                origin_message_id=origin.id, on_behalf_of=origin.sender
            )

        routed: Optional[MessageRoutable] = routable

        if self.transformer:
            routed = self.transformer.transform(
                origin=origin, agent_state=agent_state, guild_state=guild_state, routable=routable
            )

        return routed

    def get_updated_state(
        self,
        origin: "Message",
        agent_state: JsonDict,
        guild_state: JsonDict,
        routed: "MessageRoutable",
        untransformed: "MessageRoutable",
    ) -> Optional[StateUpdate]:
        """
        Get the state update for the agent or guild.

        Args:
            origin (Message): The original message.
            agent_state (JsonDict): The agent state.
            guild_state (JsonDict): The guild state.
            routed (MessageRoutable): The message after applying the route transformation.
            untransformed (MessageRoutable): The message routable before applying the route transformation.

        Returns:
            StateUpdate: The state update request.
        """
        if self.agent_state_update:
            return self.agent_state_update.transform(
                origin=origin,
                agent_state=agent_state,
                guild_state=guild_state,
                routed=routed,
                untransformed=untransformed,
            )
        else:
            return None

    def get_updated_guild_state(
        self,
        origin: "Message",
        agent_state: JsonDict,
        guild_state: JsonDict,
        routed: "MessageRoutable",
        untransformed: "MessageRoutable",
    ) -> Optional[StateUpdate]:
        """
        Get the state update for the guild.

        Args:
            origin (Message): The original message.
            agent_state (JsonDict): The agent state.
            guild_state (JsonDict): The guild state.
            routed (MessageRoutable): The message after applying the route transformation.
            untransformed (MessageRoutable): The message routable before applying the route transformation.

        Returns:
            StateUpdate: The state update request.
        """

        if self.guild_state_update:
            return self.guild_state_update.transform(
                origin=origin,
                agent_state=agent_state,
                guild_state=guild_state,
                routed=routed,
                untransformed=untransformed,
            )
        else:
            return None


class RoutingSlip(BaseModel):
    """
    Represents a routing slip for a message.

    Attributes:
        steps (List[RoutingEntry]): List of routing steps for the message. Each step is an edge in the routing slip.
    """

    steps: List[RoutingRule] = Field(default=[])

    def add_step(self, routing_entry: RoutingRule):
        """
        Add a step to the routing slip.

        Args:
            routing_entry (RoutingEntry): The routing entry to add.
        """
        self.steps.append(routing_entry)

    def get_next_steps(
        self,
        agent: AgentTag,
        agent_type: str,
        method_name: str,
        origin: RoutingOrigin,
        message_format: str,
    ) -> List[RoutingRule]:
        """
        Pop the next steps in the routing slip for a message.

        Args:
            agent (AgentTag): The agent sending the message.
            method_name (str): The method in the agent from which the message is being sent.
            origin (RoutingOriginFilter): The origin message that triggered this process.
            message_format (str): The format of the message being sent.

        Returns:
            List[RoutingEntry]: The next steps in the routing slip.
        """
        next_steps = [
            step for step in self.steps if step.is_applicable(agent, agent_type, method_name, origin, message_format)
        ]

        for next_step in next_steps:
            next_step.decrement_route_times()

        self.steps = [step for step in self.steps if not step.is_done()]

        return next_steps

    def get_steps_count(self):
        return len(self.steps)


class ForwardHeader(BaseModel):
    """
    Represents the header for a forwarded message.

    Attributes:
        origin_message_id (int): ID of the original message.
        on_behalf_of (AgentTag): The agent on whose behalf the message is forwarded.
    """

    origin_message_id: int
    on_behalf_of: AgentTag


class MessageRoutable(BaseModel):
    """
    Represents the fields of a message that can be modified by a router.

    Attributes:
        topics (Union[str, List[str]]): The topics to which the message should be published.
        recipient_list (List[AgentTag]): List of agents tagged in the message.
        payload (JsonDict): The actual content or payload of the message.
        format (str): The type of the message.
        forward_header (Optional[ForwardHeader]): The header for a forwarded message.
        context (Optional[JsonDict]): The context of the message.
    """

    topics: Union[str, List[str]]
    priority: Priority

    recipient_list: Optional[List[AgentTag]] = Field(default=[])

    payload: Annotated[JsonDict, Field(min_length=1)]
    format: Annotated[str, Field(default=MessageConstants.RAW_JSON_FORMAT, min_length=3)]

    forward_header: Optional[ForwardHeader] = None
    context: Optional[JsonDict] = Field(default=None)


class Message(BaseModel):
    """
    Represents a message to be published on the message bus.

    Attributes:
        sender (AgentTag): The sender of the message.
        topic (str): The topic to which the message belongs.
        recipient_list (List[AgentTag]): List of agents tagged in the message.
        payload (JsonDict): The actual content or payload of the message.
        format (str): The type of the message.
        in_response_to (Optional[int]): ID of the message to which this is a reply, if any.
        thread (List[int]): The list of threads to which the message belongs.
        conversation_id (Optional[int]): ID of the conversation to which the message belongs.
        forwarding_header (Optional[ForwardingHeader]): The header for a forwarded message.
        routing_slip (Optional[RoutingSlip]): The routing slip for the message.
        message_history (List[ProcessEntry]): The history of the message.
        ttl (Optional[int]): The time to live for the message.

    Raises:
        ValueError: If the provided payload is not JSON-serializable or if any of the attributes are not valid.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    sender: AgentTag

    topics: Annotated[Union[str, List[str]], Field(min_length=1)]
    recipient_list: Annotated[List[AgentTag], Field(default=[])]

    payload: Annotated[JsonDict, Field(min_length=1)]
    format: Annotated[str, Field(default=MessageConstants.RAW_JSON_FORMAT, min_length=3)]

    in_response_to: Annotated[Optional[int], Field(default=None)]
    thread: Annotated[List[int], Field(default_factory=lambda: [])]
    conversation_id: Annotated[Optional[int], Field(default=None)]

    forward_header: Annotated[Optional[ForwardHeader], Field(default=None)]

    routing_slip: Annotated[Optional[RoutingSlip], Field(default=None)]

    message_history: Annotated[List[ProcessEntry], Field(default_factory=lambda: [])]

    ttl: Annotated[Optional[int], Field(default=None)]

    is_error_message: Annotated[bool, Field(default=False)]

    traceparent: Annotated[Optional[str], Field(default=None)]

    session_state: Annotated[Optional[JsonDict], Field(default=None)]

    _id: int  # Internal backend for id
    _priority: Priority  # Internal backend for priority
    _timestamp: float  # Internal backend for timestamp

    topic_published_to: Optional[str] = None

    def __init__(self, id_obj: GemstoneID, **data: Any):
        """
        Initializes a new message.
        :param id_obj: (GemstoneID): An instance of GemstoneID used to generate the message ID, priority, and timestamp.
        :param **kwargs: message data
        """
        if not isinstance(id_obj, GemstoneID):
            raise ValueError("id_obj must be a GemstoneID")
        super().__init__(**data)
        self._id = id_obj.to_int()
        self._priority = id_obj.encoded_priority
        self._timestamp = id_obj.timestamp
        if not self.thread:
            self.thread = [self._id]

    @computed_field  # type: ignore
    @property
    def id(self) -> int:
        """
        Read-only property to get the ID of the message.

        Returns:
            int: The ID of the message.
        """
        return self._id

    @computed_field  # type: ignore
    @property
    def priority(self) -> Priority:
        """
        Read-only property to get the priority of the message.

        Returns:
            Priority: The priority of the message.
        """
        return self._priority

    @staticmethod  # type: ignore
    @field_serializer("priority", when_used="json", mode="wrap")
    def serialize_priority(priority: Priority) -> int:
        """
        Serialize a priority enum into an integer.

        Returns:
            int: The priority as an integer.
        """
        return priority.value  # pragma: no cover

    @computed_field  # type: ignore
    @property
    def timestamp(self) -> float:
        """
        Read-only property to get the timestamp of the message.

        Returns:
            float: The timestamp of the message.
        """
        return self._timestamp

    @computed_field  # type: ignore
    @property
    def current_thread_id(self) -> int:
        """
        Read-only property to get the current thread ID of the message.

        Returns:
            int: The current thread ID of the message.
        """
        return self.thread[-1]

    @computed_field  # type: ignore
    @property
    def root_thread_id(self) -> int:
        """
        Read-only property to get the root thread ID of the message.

        Returns:
            int: The root thread ID of the message.
        """
        return self.thread[0]

    def __lt__(self, other: "Message") -> bool:
        """
        Compares two messages based on their IDs.

        Args:
            other (Message): The other message to compare to.

        Returns:
            bool: True if this message's ID is less than the other message's ID, False otherwise.
        """
        if not isinstance(other, Message):
            return NotImplemented  # pragma: no cover
        return self.id < other.id

    @classmethod
    def model_validate(
        cls: type["Message"],
        obj: Any,
        *,
        strict: bool | None = None,
        from_attributes: bool | None = None,
        context: dict[str, Any] | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> "Message":
        return cls._from_dict(obj)

    @classmethod
    def model_validate_json(
        cls: type["Message"],
        json_data: str | bytes | bytearray,
        *,
        strict: bool | None = None,
        context: dict[str, Any] | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> "Message":
        """
        Custom JSON decoder for the Message class that supports different GemstoneID implementations.
        This defines how to deserialize JSON to Message objects.
        """
        json_str = json_data if isinstance(json_data, str) else json_data.decode("utf-8")
        dct = json.loads(json_str)

        return cls._from_dict(dct)

    @classmethod
    def _from_dict(cls, dct: Dict[str, Any]) -> "Message":
        # Check if the dictionary has the required fields to be a Message
        if "id" in dct:
            # Extract the id value
            id_value: int = dct["id"]
            # Create an GemstoneID instance from the id value
            id_instance: GemstoneID = GemstoneID.from_int(id_value)
            # Remove the id, priority, timestamp and computed fields from the dictionary
            # since they are not required to initialize a Message
            keys_to_remove = [
                "id",
                "priority",
                "timestamp",
                "current_thread_id",
                "root_thread_id",
            ]
            dct = {k: v for k, v in dct.items() if k not in keys_to_remove}
            return Message(id_obj=id_instance, **dct)
        else:
            raise ValueError("Message JSON must contain an id field")

    @classmethod
    def from_json(cls, json_data: str | bytes | bytearray) -> "Message":
        """
        Converts a JSON string to a Message object.

        Args:
            json_data (str): The JSON string to convert.

        Returns:
            Message: A Message object created from the JSON string.
        """
        return cls.model_validate_json(json_data)

    def to_json(self) -> str:
        """
        Converts the Message object to a JSON string.

        Returns:
            str: A JSON string representation of the Message object.
        """
        return self.model_dump_json(
            exclude={
                "current_thread_id",
                "root_thread_id",
            }
        )

    def is_tagged(self, agent_tag: AgentTag) -> bool:
        """
        Check if the message is tagged by an agent.

        Args:
            agent_tag (AgentTag): The agent tag to check.

        Returns:
            bool: True if the message is tagged by the agent, False otherwise.
        """
        return agent_tag in self.recipient_list
