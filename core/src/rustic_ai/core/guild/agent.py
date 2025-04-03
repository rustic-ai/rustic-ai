from __future__ import annotations

import asyncio
import inspect
import logging
from copy import deepcopy
from enum import Enum
from typing import Any, Callable, Dict, Generic, List, Optional, Type, TypeVar

from pydantic import BaseModel

from rustic_ai.core.agents.commons.message_formats import ErrorMessage
from rustic_ai.core.guild.agent_ext.depends import DependencyResolver
from rustic_ai.core.guild.dsl import APT, AgentSpec, GuildSpec, GuildTopics
from rustic_ai.core.guild.metaprog import AgentAnnotations
from rustic_ai.core.guild.metaprog.agent_metaclass import (
    AgentMetaclass,
    FormatMessageHandlers,
    MessageHandler,
    RawMessageHandlers,
)
from rustic_ai.core.guild.metaprog.agent_registry import AgentDependency
from rustic_ai.core.guild.metaprog.constants import MetaclassConstants
from rustic_ai.core.messaging import MDT, AgentTag, Client, Message, Priority
from rustic_ai.core.messaging.core.message import (
    ForwardHeader,
    MessageConstants,
    MessageRoutable,
    ProcessEntry,
    RoutingOrigin,
    RoutingRule,
    RoutingSlip,
    StateUpdate,
)
from rustic_ai.core.state.models import StateOwner, StateUpdateRequest
from rustic_ai.core.utils import GemstoneGenerator, GemstoneID, JsonDict
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name


class AgentType(Enum):
    """
    Enum class to represent the type of agent.
    """

    HUMAN = "human"
    BOT = "bot"


class AgentMode(Enum):
    """
    Enum class to represent the mode of the agent.
    """

    LOCAL = "local"
    REMOTE = "remote"


class Agent(Generic[APT], metaclass=AgentMetaclass):  # type: ignore
    """
    Base class for all agents
    """

    def __init__(
        self,
        agent_spec: AgentSpec[APT],
        agent_type: AgentType = AgentType.BOT,
        agent_mode: AgentMode = AgentMode.LOCAL,
        handled_formats: list = [],
    ):
        """
        Initializes a new instance of the Agent class.

        Args:
            agent_spec (AgentSpec): The specification for the agent.
            agent_type (AgentType): The type of the agent.
            agent_mode (AgentMode): The mode of the agent.
            handled_formats (list): The formats of messages handled by the agent.
        """

        self._agent_spec = agent_spec

        self.id = agent_spec.id
        self.name = agent_spec.name
        self.type = agent_type
        self.description = agent_spec.description
        self.mode = agent_mode
        self.handled_formats = handled_formats
        self.subscribed_topics = agent_spec.subscribed_topics

        self._dependency_resolvers: Dict[str, DependencyResolver] = {}

        self._agent_tag = AgentTag(id=self.id, name=self.name)

        self._state: JsonDict = {}
        self._guild_state: JsonDict = {}

    def get_spec(self) -> AgentSpec[APT]:
        """
        Converts the agent to a specification.

        Returns:
            AgentSpec: The specification for the agent.
        """
        return self._agent_spec

    @classmethod
    def get_qualified_class_name(cls):
        return f"{cls.__module__}.{cls.__name__}"

    def _set_client(self, client: Client) -> Client:
        """
        Connects the agent to the client.

        Args:
            client (ClientType): The client used to communicate with the agent.
        """

        self._client = client
        return self._client

    @classmethod
    def list_all_dependencies(cls) -> List[AgentDependency]:
        return list(cls.__annotations__[AgentAnnotations.DEPENDS_ON])

    def get_agent_tag(self) -> AgentTag:
        """
        Returns the tag for the agent.

        Returns:
            AgentTag: The tag for the agent.
        """
        return self._agent_tag

    def get_agent_state(self):
        """
        Get the state of the agent.
        """
        return self._state

    def get_guild_state(self):
        """
        Get the state of the guild.
        """
        return self._guild_state

    def _get_client(self) -> Client:
        return self._client

    def _set_generator(self, generator: GemstoneGenerator):
        """
        Sets the id generator for the agent.

        Args:
            generator (GemstoneGenerator): The id generator for the agent.

        """
        self._id_generator = generator

    def _set_guild_spec(self, guild_spec: GuildSpec):
        """
        Sets the guild id for the agent.

        Args:
            guild_spec (GuildSpec): The spec for the guild this agent belongs to.
        """
        self.guild_spec = guild_spec

    @property
    def guild_id(self) -> str:
        return self.guild_spec.id

    def _set_dependency_resolvers(self, dependency_resolvers: Dict[str, DependencyResolver]):
        """
        Sets the dependency resolvers for the agent.

        Args:
            dependency_resolvers (Dict[str, DependencyResolver]): The dependency resolvers for the agent.
        """
        self._dependency_resolvers = dependency_resolvers

    def _generate_id(self, priority: Priority) -> GemstoneID:
        """
        Generates a unique identifier for the agent.

        Args:
            priority (Priority): The priority of the agent.

        Returns:
            str: A unique identifier for the agent.
        """
        return self._id_generator.get_id(priority)

    def _on_message(self, message: Message) -> None:
        """
        Handles a message received by the agent.

        Args:
            message (Message): The message received by the agent.
        """
        handlers = self._get_applicable_processors(message)

        for name, mh in handlers.items():
            mh.handler(self, message)

    def _make_process_context(
        self,
        message: Message,
        method_name: str,
        payload_type: Type[MDT],
        on_send_fixtures: List[Callable],
        on_error_filters: List[Callable],
        outgoing_message_modifiers: List[Callable],
    ) -> ProcessContext:
        """
        Creates a process context for the agent.

        Args:
            message (Message): The message to be processed.

        Returns:
            ProcessContext: The process context for the agent.
        """
        return ProcessContext(
            agent=self,
            message=message,
            method_name=method_name,
            payload_type=payload_type,
            on_send_fixtures=on_send_fixtures,
            on_error_fixtures=on_error_filters,
            outgoing_message_modifiers=outgoing_message_modifiers,
        )

    def _get_applicable_processors(self, message: Message):
        fh: FormatMessageHandlers = self.__rustic_agent_message_handlers__  # type: ignore
        rh: RawMessageHandlers = self.__rustic_agent_raw_message_handlers__  # type: ignore

        format_handlers: Dict[str, MessageHandler] = {}
        raw_handlers: Dict[str, MessageHandler] = {}

        if message.topic_published_to not in GuildTopics.ESSENTIAL_TOPICS:
            format_handlers = fh.get_handlers_for_format(message.format)
            raw_handlers = rh.get_handlers()
        else:
            format_handlers = fh.get_essential_handlers_for_format(message.format)
            raw_handlers = rh.get_essential_handlers()

        handlers = {**format_handlers, **raw_handlers}
        return handlers


AT = TypeVar("AT", bound=Agent)

WRAPPER_ASSIGNMENTS = (
    "__module__",
    "__name__",
    "__qualname__",
    "__doc__",
)
WRAPPER_UPDATED = ("__dict__",)


def _update_wrapper(wrapper, func):
    for attr in WRAPPER_ASSIGNMENTS:
        try:
            value = getattr(func, attr)
        except AttributeError:  # pragma: no cover
            pass
        else:
            setattr(wrapper, attr, value)

    dict_attr = getattr(func, "__dict__", {}).copy()

    try:
        if "__annotations__" in dict_attr:  # pragma: no cover
            dict_attr.pop("__annotations__")

        if "__wrapped__" in dict_attr:  # pragma: no cover
            dict_attr.pop("__wrapped__")
        wrapper.__dict__.update(dict_attr)
    except KeyError:  # pragma: no cover
        pass

    # We do not use __wrapped__ to avoid modifying the wrappers signature
    # on inspection using inspect.signature(wrapper) so we store the
    # original function in a special attribute __wfn__
    setattr(wrapper, "__wfn__", func)

    return wrapper


class ProcessContext[MDT]:
    """
    Represents the context of the message to be processed by the agent. This is used within the method to send new messages in the system.
    """

    def __init__(
        self,
        agent: Agent,
        message: Message,
        method_name: str,
        payload_type: Type[MDT] = JsonDict,  # type: ignore
        on_send_fixtures: List[Callable] = [],
        on_error_fixtures: List[Callable] = [],
        outgoing_message_modifiers: List[Callable] = [],
    ):
        self._agent = agent
        self._origin_message = message
        self._method_name = method_name
        self._payload_type = payload_type
        self._sent_messages: List[Message] = []
        self._sent_errors: List[Message] = []

        self._on_send_fixtures = on_send_fixtures
        self._on_error_fixtures = on_error_fixtures
        self._outgoing_message_modifiers = outgoing_message_modifiers
        self._current_routing_step: Optional[RoutingRule] = None
        self._remaining_routing_steps = 0

        self._routing_origin = RoutingOrigin(
            origin_sender=self._origin_message.sender,
            origin_topic=self._origin_message.topic_published_to,
            origin_message_format=self._origin_message.format,
        )

        self._msg_context: JsonDict = deepcopy(message.session_state) if message.session_state else {}

    def _get_id(self, priority: Priority) -> GemstoneID:
        return self._agent._generate_id(priority)

    @property
    def _client(self) -> Client:
        return self.agent._client

    @property
    def payload(self) -> MDT:
        if self._payload_type == JsonDict:
            return self._origin_message.payload  # type: ignore
        else:
            return self._payload_type.model_validate(self._origin_message.payload)  # type: ignore

    @property
    def message(self) -> Message:
        return self._origin_message

    @property
    def agent(self) -> Agent:
        return self._agent

    @property
    def sent_messages(self) -> List[Message]:  # pragma: no cover
        return self._sent_messages

    @property
    def sent_errors(self) -> List[Message]:  # pragma: no cover
        return self._sent_errors

    @property
    def sent_message_count(self) -> int:  # pragma: no cover
        return len(self._sent_messages)

    @property
    def sent_error_count(self) -> int:  # pragma: no cover
        return len(self._sent_errors)

    @property
    def method_name(self) -> str:  # pragma: no cover
        return self._method_name

    @property
    def processor_message_type(self) -> str:  # pragma: no cover
        return self._payload_type.__name__

    @property
    def current_routing_step(self) -> Optional[RoutingRule]:  # pragma: no cover
        return self._current_routing_step

    @property
    def remaining_routing_steps(self) -> int:  # pragma: no cover
        return self._remaining_routing_steps

    @property
    def routing_origin(self) -> RoutingOrigin:
        return self._routing_origin

    def update_context(self, updates: JsonDict) -> None:
        self._msg_context |= updates

    def get_context(self) -> JsonDict:
        return deepcopy(self._msg_context)  # deepcopy to prevent modification of the original context

    def add_routing_step(self, routing_entry: RoutingRule) -> None:
        """
        Adds a new routing step to the routing slip of the message.
        """

        if not self._origin_message.routing_slip:
            self._origin_message.routing_slip = RoutingSlip()

        self._origin_message.routing_slip.add_step(routing_entry)

    def send_error(self, payload: BaseModel) -> List[GemstoneID]:
        """
        Sends an error message with the BaseModel payload using the routing rules from the routing slip of the origin message.
        If no routing rules are found, the message is sent using the default routing rule.
        """
        format = get_qualified_class_name(payload.__class__)
        data_dict = payload.model_dump()

        return self.send_dict(data_dict, format, error_message=True)

    def send(
        self,
        payload: BaseModel,
        new_thread: bool = False,
        forwarding: bool = False,
    ) -> List[GemstoneID]:
        """
        Sends a new message with the BaseModel payload using the routing rules from the routing slip of the origin message.
        If no routing rules are found, the message is sent using the default routing rule.
        """

        format = get_qualified_class_name(payload.__class__)
        data_dict = payload.model_dump()

        return self.send_dict(data_dict, format, new_thread, forwarding)

    def send_dict(
        self,
        payload: JsonDict,
        format: str = MessageConstants.RAW_JSON_FORMAT,
        new_thread: bool = False,
        forwarding: bool = False,
        error_message: bool = False,
    ) -> List[GemstoneID]:
        """
        Sends a new message with the JsonDict payload using the routing rules from the routing slip of the origin message.
        If no routing rules are found, the message is sent using the default routing rule.
        """

        if error_message and self._on_error_fixtures:
            for fixture in self._on_error_fixtures:
                try:
                    fixture(self.agent, self)  # type: ignore
                except Exception as e:  # pragma: no cover
                    logging.exception(f"Error in on error fixture {fixture.__name__}: {e}")

        if not error_message and self._on_send_fixtures:
            for fixture in self._on_send_fixtures:
                try:
                    fixture(self.agent, self)  # type: ignore
                except Exception as e:  # pragma: no cover
                    logging.exception(f"Error in on send fixture {fixture.__name__}: {e}")

        next_steps: List[RoutingRule] = []
        if self._origin_message.routing_slip:
            next_steps = self._origin_message.routing_slip.get_next_steps(
                self._agent.get_agent_tag(),
                self._agent.get_qualified_class_name(),
                self._method_name,
                self.routing_origin,
                format,
            )

        if not next_steps:
            next_steps = [
                RoutingRule(
                    agent=self._agent.get_agent_tag(),
                    method_name=self._method_name,
                    message_format=format,
                )
            ]

        messages: List[GemstoneID] = []

        self._remaining_routing_steps = len(next_steps)

        logging.debug(f"Agent [{self.agent.name}] from method [{self.method_name}] with rules :\n{next_steps}\n")

        for step in next_steps:
            msgid = self._prepare_and_send_message(payload, format, new_thread, forwarding, error_message, step)
            if msgid:
                messages.append(msgid)
            self._remaining_routing_steps -= 1

        return messages

    def _prepare_and_send_message(
        self,
        payload: JsonDict,
        format: str,
        new_thread: bool,
        forwarding: bool,
        error_message: bool,
        step: RoutingRule,
    ) -> Optional[GemstoneID]:
        self._current_routing_step = step

        agent_state = self.agent.get_agent_state()
        guild_state = self.agent.get_guild_state()

        routable = MessageRoutable(
            topics=self._origin_message.topics,
            priority=self._origin_message.priority,
            payload=payload,
            format=format,
            forward_header=self._origin_message.forward_header,
            context=self.get_context(),
        )

        routed = step.apply(self._origin_message, agent_state, guild_state, routable, forwarding)

        if routed is None:
            return None

        guild_state_update: Optional[StateUpdate] = step.get_updated_guild_state(
            self._origin_message,
            agent_state,
            guild_state,
            routed,
            routable,
        )

        if guild_state_update:

            gsu = StateUpdateRequest(
                state_owner=StateOwner.GUILD,
                guild_id=self._agent.guild_id,
                update_format=guild_state_update.update_format,
                state_update=guild_state_update.state_update,
            )

            self._raw_send(
                priority=Priority.NORMAL,
                topics=[GuildTopics.GUILD_STATUS_TOPIC],
                payload=gsu.model_dump(),
                format=get_qualified_class_name(StateUpdateRequest),
                in_response_to=self._origin_message.id,
            )

        agent_state_update: Optional[StateUpdate] = step.get_updated_state(
            self._origin_message,
            agent_state,
            guild_state,
            routed,
            routable,
        )

        if agent_state_update:

            asu = StateUpdateRequest(
                state_owner=StateOwner.AGENT,
                guild_id=self._agent.guild_id,
                agent_id=self._agent.id,
                update_format=agent_state_update.update_format,
                state_update=agent_state_update.state_update,
            )

            self._raw_send(
                priority=Priority.NORMAL,
                topics=[GuildTopics.GUILD_STATUS_TOPIC],
                payload=asu.model_dump(),
                format=get_qualified_class_name(StateUpdateRequest),
                in_response_to=self._origin_message.id,
            )

        msg_id = self._get_id(routed.priority)
        msg_thread = self._origin_message.thread.copy()
        if new_thread:
            msg_thread.append(msg_id.to_int())

        message_history = self._origin_message.message_history.copy()
        message_history.append(
            ProcessEntry(agent=self._agent.get_agent_tag(), origin=self._origin_message.id, result=msg_id.to_int())
        )

        routing_slip = (
            self._origin_message.routing_slip.model_copy(deep=True) if self._origin_message.routing_slip else None
        )

        routed_context = routed.context if routed.context else {}

        new_message = Message(
            id_obj=msg_id,
            topics=routed.topics,
            sender=self._agent.get_agent_tag(),
            payload=routed.payload,
            format=routed.format,
            in_response_to=self._origin_message.id,
            recipient_list=routed.recipient_list,
            thread=msg_thread,
            ttl=self._origin_message.ttl,
            message_history=message_history,
            forward_header=routed.forward_header,
            routing_slip=routing_slip,
            is_error_message=error_message,
            traceparent=self._origin_message.traceparent,
            session_state=self.get_context() | routed_context,
        )

        for modifier in self._outgoing_message_modifiers:
            try:
                modifier(self.agent, self, new_message)
            except Exception as e:  # pragma: no cover
                logging.exception(f"Error in outgoing message modifier {modifier.__name__}: {e}")

        self._client.publish(new_message)

        logging.debug(
            f"Agent [{self.agent.name}] from method [{self.method_name}] sent message for rule [{step}]:\n{new_message.model_dump_json()}\n"
        )

        if not error_message:
            self._sent_messages.append(new_message)
        else:
            self._sent_errors.append(new_message)

        self._current_routing_step = None

        return msg_id

    def _raw_send(
        self,
        priority: Priority,
        topics: List[str],
        payload: JsonDict,
        format: str,
        in_response_to: Optional[int] = None,
        recipient_list: List[AgentTag] = [],
        ttl: Optional[int] = None,
        message_history: List[ProcessEntry] = [],
        forward_header: Optional[ForwardHeader] = None,
        routing_slip: Optional[RoutingSlip] = None,
        is_error_message: bool = False,
        traceparent: Optional[str] = None,
        session_state: Optional[JsonDict] = None,
    ) -> None:
        msg_id = self._get_id(priority)
        thread = self._origin_message.thread.copy()

        self._client.publish(
            Message(
                id_obj=msg_id,
                topics=topics,
                sender=self._agent.get_agent_tag(),
                payload=payload,
                format=format,
                in_response_to=in_response_to,
                recipient_list=recipient_list,
                thread=thread,
                ttl=ttl,
                message_history=message_history,
                forward_header=forward_header,
                routing_slip=routing_slip,
                is_error_message=is_error_message,
                traceparent=traceparent,
                session_state=session_state,
            )
        )


class ProcessorHelper:
    @staticmethod
    def get_before_fixtures(cls: Type[AT]) -> List[Callable]:
        return getattr(cls, MetaclassConstants.BEFORE_FIXTURES, [])

    @staticmethod
    def get_after_fixtures(cls: Type[AT]) -> List[Callable]:
        return getattr(cls, MetaclassConstants.AFTER_FIXTURES, [])

    @staticmethod
    def get_on_send_fixtures(cls: Type[AT]) -> List[Callable]:
        return getattr(cls, MetaclassConstants.ON_SEND_FIXTURES, [])

    @staticmethod
    def get_on_error_fixtures(cls: Type[AT]) -> List[Callable]:
        return getattr(cls, MetaclassConstants.ON_ERROR_FIXTURES, [])

    @staticmethod
    def get_message_mod_fixtures(cls: Type[AT]) -> List[Callable]:
        return getattr(cls, MetaclassConstants.MESSAGE_MOD_FIXTURES, [])

    @staticmethod
    def resolve_dependency(
        resolver: DependencyResolver,
        dep: AgentDependency,
        guild_id: str,
        agent_id: str,
    ):
        if dep.guild_level:
            return resolver.get_or_resolve(guild_id=guild_id)
        else:
            return resolver.get_or_resolve(guild_id=guild_id, agent_id=agent_id)

    @staticmethod
    def run_coroutine(self, func, dependencies, context):
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as re:
            logging.debug(f"Error getting running loop: {re}")
            loop = None

        if loop and loop.is_running():
            loop.create_task(func(self, context, **dependencies))
        else:
            asyncio.run(func(self, context, **dependencies))

    @staticmethod
    def execute_before_fixtures(processor, context):
        before_fixtures = ProcessorHelper.get_before_fixtures(processor.__class__)
        for bf in before_fixtures:
            try:
                bf(processor, context)
            except Exception as e:  # pragma: no cover
                logging.exception(f"Error in before fixture {bf.__name__}: {e}")

    @staticmethod
    def execute_after_fixtures(processor, context):
        after_fixtures = ProcessorHelper.get_after_fixtures(processor.__class__)
        for af in after_fixtures:
            try:
                af(processor, context)
            except Exception as e:  # pragma: no cover
                logging.exception(f"Error in after fixture {af.__name__}: {e}")


def processor(
    clz: Type[MDT],
    predicate: Optional[Callable[[AT, Message], bool]] = None,
    handle_essential: bool = False,
    depends_on: List[str | AgentDependency] = [],
):
    def decorator(func: Callable[[AT, ProcessContext[MDT]], None]):

        deps: List[AgentDependency] = [
            dep if isinstance(dep, AgentDependency) else AgentDependency.from_string(dep) for dep in depends_on
        ]

        def wrapper(self: AT, msg: Message) -> None:

            if (predicate is None or predicate(self, msg)) and (
                not self._agent_spec.act_only_when_tagged or msg.is_tagged(self.get_agent_tag())
            ):
                runtime_predicate = self._agent_spec.predicates.get(func.__name__)

                should_process = True

                if runtime_predicate:
                    try:
                        should_process = runtime_predicate.evaluate(
                            msg.model_dump(), self.get_agent_state(), self.get_guild_state()
                        )
                    except Exception as e:  # pragma: no cover
                        logging.exception(
                            f"Error in predicate for method [func.__name__]: {runtime_predicate.expression}: {e}"
                        )
                        # TODO: SEND ERROR MESSAGE
                        should_process = False

                if not should_process:
                    logging.debug(
                        f"Predicate {predicate} on method [{func.__name__}] failed for message:\n {msg.model_dump()}\n"
                    )
                    return

                dependencies = {
                    dep.variable_name: ProcessorHelper.resolve_dependency(
                        self._dependency_resolvers[dep.dependency_key], dep, self.guild_id, self.id
                    )
                    for dep in deps
                }

                logging.debug(f"Processor [{func.__name__}] running for message:\n {msg.model_dump_json()}\n")

                send_fixtures = ProcessorHelper.get_on_send_fixtures(self.__class__)
                error_fixtures = ProcessorHelper.get_on_error_fixtures(self.__class__)
                mod_fixtures = ProcessorHelper.get_message_mod_fixtures(self.__class__)
                context = self._make_process_context(
                    msg, func.__name__, clz, send_fixtures, error_fixtures, mod_fixtures
                )

                ProcessorHelper.execute_before_fixtures(self, context)

                try:
                    if inspect.iscoroutinefunction(func):
                        ProcessorHelper.run_coroutine(self, func, dependencies, context)
                    else:
                        func(self, context, **dependencies)
                except Exception as e:  # pragma: no cover
                    logging.exception(f"Error in processor {func.__name__}: {e}")
                    context.send_error(
                        ErrorMessage(
                            agent_type=self.get_qualified_class_name(),
                            error_type="UNHANDLED_EXECEPTION",
                            error_message=str(e),
                        )
                    )

                ProcessorHelper.execute_after_fixtures(self, context)
                return
            else:
                logging.debug(
                    f"Predicate {predicate} on method [{func.__name__}] failed for message:\n {msg.model_dump()}\n"
                )
                return

        wrapper.__annotations__ = {
            AgentAnnotations.ISHANDLER: True,
            AgentAnnotations.MESSAGE_FORMAT: clz,
            AgentAnnotations.HANDLE_ESSENTIAL: handle_essential,
            AgentAnnotations.HANDLES_RAW: clz == JsonDict,
            AgentAnnotations.DEPENDS_ON: deps,
        }

        return _update_wrapper(wrapper, func)

    return decorator


class AgentFixtures:
    """
    A class to hold before, after, wrap, and on_send fixtures for agents. These are annotations that can be used
    to decorate methods in the agent class that would be called before, after, or around the processing of messages.
    """

    @staticmethod
    def before_process(func: Callable[[Any, ProcessContext[MDT]], None]) -> Callable[[Any, ProcessContext[MDT]], None]:
        """
        Decorator for a method that should be called before the processing of a message.

        Args:
            func (Callable[[AT, ProcessContext[MDT]], None]): The method to be called before the processing of a message.

        Returns:
            Callable[[AT, ProcessContext[MDT]], None]: The decorated method.
        """
        func.__annotations__[AgentAnnotations.IS_BEFORE_PROCESS_FIXTURE] = True
        return func

    @staticmethod
    def after_process(func: Callable[[Any, ProcessContext[MDT]], None]) -> Callable[[Any, ProcessContext[MDT]], None]:
        """
        Decorator for a method that should be called after the processing of a message.

        Args:
            func (Callable[[AT, ProcessContext[MDT]], None]): The method to be called after the processing of a message.

        Returns:
            Callable[[AT, ProcessContext[MDT]], None]: The decorated method.
        """
        func.__annotations__[AgentAnnotations.IS_AFTER_PROCESS_FIXTURE] = True
        return func

    @staticmethod
    def on_send(func: Callable[[Any, ProcessContext[MDT]], None]) -> Callable[[Any, ProcessContext[MDT]], None]:
        """
        Decorator for a method that should be called when a message is sent.

        Args:
            func (Callable[[AT, ProcessContext[MDT]], None]): The method to be called when a message is sent.

        Returns:
            Callable[[AT, ProcessContext[MDT]], None]: The decorated method.
        """
        func.__annotations__[AgentAnnotations.IS_ON_SEND_FIXTURE] = True
        return func

    @staticmethod
    def on_send_error(func: Callable[[Any, ProcessContext[MDT]], None]) -> Callable[[Any, ProcessContext[MDT]], None]:
        """
        Decorator for a method that should be called when an error message is sent.

        Args:
            func (Callable[[AT, ProcessContext[MDT]], None]): The method to be called when an error message is sent.

        Returns:
            Callable[[AT, ProcessContext[MDT]], None]: The decorated method.
        """
        func.__annotations__[AgentAnnotations.IS_ON_SEND_ERROR_FIXTURE] = True
        return func

    @staticmethod
    def outgoing_message_modifier(
        func: Callable[[Any, ProcessContext[MDT], Message], None]
    ) -> Callable[[Any, ProcessContext[MDT], Message], None]:
        """
        Decorator for a method that should be called when a message is sent.

        Args:
            func (Callable[[AT, ProcessContext[MDT]], None]): The method to be called when a message is sent.

        Returns:
            Callable[[AT, ProcessContext[MDT]], None]: The decorated method.
        """
        func.__annotations__[AgentAnnotations.IS_MESSAGE_MOD_FIXTURE] = True
        return func
