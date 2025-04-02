from typing import List, Optional, Union

from pydantic import BaseModel

from rustic_ai.core.guild import Agent, AgentMode, AgentSpec, AgentType, agent
from rustic_ai.core.messaging.core import JsonDict
from rustic_ai.core.messaging.core.message import Message, MessageConstants, RoutingSlip
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.gemstone_id import GemstoneID
from rustic_ai.core.utils.priority import Priority


class PublishMixin:
    def publish(  # type: ignore
        self: Agent,  # type: ignore
        topic: str,
        payload: BaseModel,
        priority: Priority = Priority.NORMAL,
        thread: list[int] = [],
        in_response_to: Optional[int] = None,
        recipient_list: list = [],
        routing_slip: Optional[RoutingSlip] = None,
    ) -> GemstoneID:  # type: ignore
        """
        Publishes a message to the message bus.
        """
        return self.publish_dict(  # type: ignore
            topic=topic,
            payload=payload,
            format=get_qualified_class_name(payload.__class__),
            priority=priority,
            thread=thread,
            in_response_to=in_response_to,
            recipient_list=recipient_list,
            routing_slip=routing_slip,
        )

    def publish_dict(  # type: ignore
        self: Agent,  # type: ignore
        topic: str,
        payload: Union[BaseModel, JsonDict],
        format: Union[type[BaseModel], str] = MessageConstants.RAW_JSON_FORMAT,
        priority: Priority = Priority.NORMAL,
        thread: list[int] = [],
        in_response_to: Optional[int] = None,
        recipient_list: list = [],
        routing_slip: Optional[RoutingSlip] = None,
        msg_id: Optional[GemstoneID] = None,
    ) -> GemstoneID:  # type: ignore
        """
        Publishes a message to the message bus.

        Args:
            topic (str): The topic to which the message belongs.
            payload (Dict[str, JsonValue]): The actual content or payload of the message.
            format (str): The type of the message.
            priority (Priority): The priority of the message.
            in_response_to (int): ID of the message to which this is a reply, if any.
            thread (list[int]): The list of threads to which the message belongs.
            recipient_list (List[str]): List of agents tagged in the message.
        """

        if isinstance(format, type):
            format = get_qualified_class_name(format)

        if not msg_id:
            msg_id = self._generate_id(priority)

        payload = payload.model_dump() if isinstance(payload, BaseModel) else payload

        msg_thread = thread.copy()
        if in_response_to and in_response_to not in msg_thread:
            msg_thread.append(in_response_to)

        self._client.publish(
            Message(
                topics=topic,
                sender=self.get_agent_tag(),
                format=format,
                payload=payload,
                id_obj=msg_id,
                in_response_to=in_response_to,
                recipient_list=recipient_list,
                thread=msg_thread,
                routing_slip=routing_slip,
            )
        )

        return msg_id


class ProbeAgent(Agent, PublishMixin):
    """An agent used as probe in writing Agent test cases"""

    def __init__(
        self,
        agent_spec: AgentSpec,
    ) -> None:
        super().__init__(agent_spec=agent_spec, agent_type=AgentType.BOT, agent_mode=AgentMode.LOCAL)
        self.received_messages: List[Message] = []

    @agent.processor(JsonDict)
    def collect_message(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        self.received_messages.append(ctx.message.model_copy(deep=True))

    def get_messages(self):
        self.received_messages.sort()
        return self.received_messages

    def clear_messages(self):
        self.received_messages = []


class EssentialProbeAgent(Agent, PublishMixin):
    """An agent used as probe in writing Agent test cases"""

    def __init__(
        self,
        agent_spec: AgentSpec,
    ) -> None:
        super().__init__(agent_spec=agent_spec, agent_type=AgentType.BOT, agent_mode=AgentMode.LOCAL)
        self.received_messages: List[Message] = []

    @agent.processor(JsonDict, handle_essential=True)
    def collect_message(self, ctx: agent.ProcessContext[JsonDict]) -> None:
        self.received_messages.append(ctx.message.model_copy(deep=True))

    def get_messages(self):
        self.received_messages.sort()
        return self.received_messages

    def clear_messages(self):
        self.received_messages = []
