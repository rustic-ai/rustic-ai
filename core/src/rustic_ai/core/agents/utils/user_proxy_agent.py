from datetime import datetime
import json
import logging
import re
from typing import Dict, List

from pydantic import BaseModel
import pydantic_core

from rustic_ai.core import Message, Priority
from rustic_ai.core.agents.system.models import (
    GuildUpdatedAnnouncement,
    StopGuildRequest,
)
from rustic_ai.core.guild import BaseAgentProps
from rustic_ai.core.guild.agent import (
    Agent,
    AgentType,
    ProcessContext,
    SelfReadyNotification,
    processor,
)
from rustic_ai.core.guild.agent_ext.mixins.guild_refresher import GuildRefreshMixin
from rustic_ai.core.guild.agent_ext.mixins.health import (
    AgentsHealthReport,
    HealthConstants,
    Heartbeat,
)
from rustic_ai.core.guild.dsl import GuildSpec, GuildTopics
from rustic_ai.core.messaging.core.message import (
    AgentTag,
    ForwardHeader,
    JsonDict,
    RoutingDestination,
    RoutingRule,
)
from rustic_ai.core.ui_protocol.types import FilesWithTextFormat, TextFormat
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name


class Participant(BaseModel):
    id: str
    name: str
    type: str


class ParticipantList(BaseModel):
    participants: List[Participant]


class ParticipantListRequest(BaseModel):
    guild_id: str


class UserProxyAgentProps(BaseAgentProps):
    user_id: str


def user_topic_filter(upa: "UserProxyAgent", message: Message) -> bool:
    return upa.user_topic == message.topic_published_to


def outgoing_message_filter(upa: "UserProxyAgent", message: Message) -> bool:
    is_from_outbox = (
        message.topic_published_to == upa.user_outbox_topic or message.topic_published_to == upa.BROADCAST_TOPIC
    )
    is_tagged = message.is_tagged(upa.get_agent_tag())
    is_sent_by_me = upa.get_agent_tag() == message.sender
    return (is_from_outbox or is_tagged) and not is_sent_by_me


def system_req_filter(upa: "UserProxyAgent", message: Message) -> bool:
    return message.topic_published_to == upa.guild_requests_topic


class UserProxyAgent(Agent[UserProxyAgentProps], GuildRefreshMixin):

    BROADCAST_TOPIC = "user_message_broadcast"

    def __init__(self):
        self.user_id = self.config.user_id
        self.user_topic = UserProxyAgent.get_user_inbox_topic(self.user_id)
        self.user_outbox_topic = UserProxyAgent.get_user_outbox_topic(self.user_id)
        self.user_notifications_topic = UserProxyAgent.get_user_notifications_topic(self.user_id)
        self.user_system_notification_topic = UserProxyAgent.get_user_system_notifications_topic(self.user_id)
        self.guild_requests_topic = UserProxyAgent.get_user_system_requests_topic(self.user_id)

        self.guilds_agents_ats: Dict[str, AgentTag] = {}
        self._tag_pattern = self._build_tag_pattern()

    @processor(Message, user_topic_filter)
    def unwrap_and_forward_message(self, ctx: ProcessContext[Message]) -> None:

        unwrapped_message = ctx.payload

        msg_content = json.dumps(unwrapped_message.payload)

        if unwrapped_message.format in [
            get_qualified_class_name(TextFormat),
            get_qualified_class_name(FilesWithTextFormat),
        ]:
            tagged_users = self.find_tagged_users(msg_content)
            unwrapped_message.payload["tagged_users"] = json.dumps(
                tagged_users, default=pydantic_core.to_jsonable_python
            )

        tagged_users = self.find_tagged_users(msg_content)

        # Publish the message to the notification topic so it is recorded
        # This is useful for when user fetches historical messages
        notification_rule = RoutingRule(
            agent=ctx.agent.get_agent_tag(),
            destination=RoutingDestination(
                topics=self.user_notifications_topic,
                priority=unwrapped_message.priority,
                recipient_list=unwrapped_message.recipient_list + tagged_users,
            ),
            mark_forwarded=True,
        )

        ctx.add_routing_step(notification_rule)

        routing_entry = RoutingRule(
            agent=ctx.agent.get_agent_tag(),
            destination=RoutingDestination(
                topics=unwrapped_message.topics,
                priority=unwrapped_message.priority,
                recipient_list=unwrapped_message.recipient_list + tagged_users,
            ),
        )

        ctx.add_routing_step(routing_entry)

        for route in self.guild_spec.routes.steps:
            ctx.add_routing_step(route.model_copy(deep=True))

        if not unwrapped_message.recipient_list:
            broadcast_route = RoutingRule(
                agent=ctx.agent.get_agent_tag(),
                destination=RoutingDestination(
                    topics=UserProxyAgent.BROADCAST_TOPIC,
                    priority=unwrapped_message.priority,
                    recipient_list=unwrapped_message.recipient_list + tagged_users,
                ),
                mark_forwarded=True,
            )
            ctx.add_routing_step(broadcast_route)

        if unwrapped_message.routing_slip:
            for routing_rule in unwrapped_message.routing_slip.steps:
                ctx.add_routing_step(routing_rule)

        ctx.send_dict(unwrapped_message.payload, format=unwrapped_message.format)

    @processor(JsonDict, predicate=outgoing_message_filter)
    def forward_message_to_user(self, ctx: ProcessContext[JsonDict]) -> None:

        routing_entry = RoutingRule(
            agent=ctx.agent.get_agent_tag(),
            destination=RoutingDestination(
                topics=self.user_notifications_topic,
            ),
        )

        ctx.add_routing_step(routing_entry)

        ctx.send_dict(ctx.payload, format=ctx.message.format, forwarding=True)

    @staticmethod
    def get_user_agent_id(user_id: str) -> str:
        return f"upa-{user_id}"

    @staticmethod
    def get_user_inbox_topic(user_id: str) -> str:
        return f"user:{user_id}"

    @staticmethod
    def get_user_outbox_topic(user_id: str) -> str:
        return f"user_outbox:{user_id}"

    @staticmethod
    def get_user_notifications_topic(user_id: str) -> str:
        return f"user_notifications:{user_id}"

    @staticmethod
    def get_user_system_requests_topic(user_id: str) -> str:
        return f"user_system:{user_id}"

    @staticmethod
    def get_user_system_notifications_topic(user_id: str) -> str:
        return f"user_system_notification:{user_id}"

    @staticmethod
    def _get_guild_agents_ats(guild_spec: GuildSpec) -> Dict[str, AgentTag]:
        tags = guild_spec.get_guild_agents()
        ats = {}
        for tag in tags:
            id_at = f"@{tag.id}"
            name_at = f"@{tag.name}"

            ats[id_at] = tag
            ats[name_at] = tag

        return ats

    def _build_tag_pattern(self):
        """Build regex pattern from actual agent names, sorted by length (longest first)"""
        if not self.guilds_agents_ats:
            return None

        # Sort tags by length (longest first) to match longer names before shorter ones
        sorted_tags = sorted(self.guilds_agents_ats.keys(), key=len, reverse=True)
        # Escape special regex characters in agent names
        escaped_tags = [re.escape(tag) for tag in sorted_tags]
        # Create pattern like: @Echo Agent|@Echo|@John
        pattern = "|".join(escaped_tags)
        return re.compile(pattern)

    def _get_participant_list(self):
        self.guilds_agents_ats = self._get_guild_agents_ats(self.guild_spec)
        self._tag_pattern = self._build_tag_pattern()
        participants = []
        for agent in self.guild_spec.agents:
            category = AgentType.BOT
            if agent.class_name == UserProxyAgent.get_qualified_class_name():
                category = AgentType.HUMAN
            participant = Participant(id=agent.id, name=agent.name, type=category.value)
            participants.append(participant)
        sorted_participants = sorted(participants, key=lambda x: x.name)
        result = ParticipantList(participants=sorted_participants).model_dump()
        return result

    def guild_refresh_handler(self, ctx: ProcessContext[GuildUpdatedAnnouncement]) -> None:
        participants = self._get_participant_list()
        ctx._direct_send(
            priority=Priority.NORMAL,
            payload=participants,
            format=get_qualified_class_name(ParticipantList),
            topics=[self.user_system_notification_topic],
        )

    def find_tagged_users(self, message: str) -> List[AgentTag]:
        if not self._tag_pattern:
            return []

        found_user_tags = set(re.findall(self._tag_pattern, message))

        return [self.guilds_agents_ats[tag] for tag in found_user_tags]

    @processor(ParticipantListRequest, predicate=system_req_filter)
    def handle_participants_request(self, ctx: ProcessContext[ParticipantListRequest]):
        participants = self._get_participant_list()
        ctx._direct_send(
            priority=Priority.NORMAL,
            payload=participants,
            format=get_qualified_class_name(ParticipantList),
            topics=[self.user_system_notification_topic],
        )

    @processor(StopGuildRequest, predicate=system_req_filter)
    def handle_stop_guild_request(self, ctx: ProcessContext[StopGuildRequest]):
        stopReq = ctx.payload.model_dump()
        ctx._direct_send(
            priority=Priority.NORMAL,
            format=get_qualified_class_name(StopGuildRequest),
            payload=stopReq,
            topics=[GuildTopics.SYSTEM_TOPIC],
            forward_header=ForwardHeader(origin_message_id=ctx.message.id, on_behalf_of=ctx.message.sender),
        )

    @processor(AgentsHealthReport, handle_essential=True)
    def handle_agents_health_report(self, ctx: ProcessContext[AgentsHealthReport]):
        ctx._direct_send(
            priority=Priority.NORMAL,
            payload=ctx.payload.model_dump(),
            format=get_qualified_class_name(AgentsHealthReport),
            topics=[self.user_system_notification_topic],
            forward_header=ForwardHeader(origin_message_id=ctx.message.id, on_behalf_of=ctx.message.sender),
        )
        participants = self._get_participant_list()
        ctx._direct_send(
            priority=Priority.NORMAL,
            payload=participants,
            format=get_qualified_class_name(ParticipantList),
            topics=[self.user_system_notification_topic],
        )

    @processor(
        SelfReadyNotification,
        predicate=lambda self, msg: msg.sender == self.get_agent_tag() and msg.topic_published_to == self._self_inbox,
        handle_essential=True,
    )
    def send_initial_participants(self, ctx: ProcessContext[SelfReadyNotification]) -> None:
        """
        Sends the first heartbeat when the agent is ready.
        """
        if not isinstance(self, Agent):
            return

        logging.info(f"Received SelfReadyNotification[{self.name}] from {ctx.message.id}")
        logging.info(f"{ctx.message.model_dump()}")

        logging.info(f"Sending first heartbeat for {self.get_agent_tag()}")

        hr = self.healthcheck(datetime.now())
        ctx._direct_send(
            priority=Priority.HIGH,
            topics=[HealthConstants.HEARTBEAT_TOPIC],
            payload=hr.model_dump(),
            format=get_qualified_class_name(Heartbeat),
            recipient_list=[],
            in_response_to=ctx.message.id,
        )  # TODO - remove this once multiple handlers for message type are supported

        participants = self._get_participant_list()
        ctx._direct_send(
            priority=Priority.NORMAL,
            payload=participants,
            format=get_qualified_class_name(ParticipantList),
            topics=[self.user_system_notification_topic],
        )
