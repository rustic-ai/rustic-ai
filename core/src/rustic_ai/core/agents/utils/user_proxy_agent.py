import json
import re
from typing import Dict, List

import pydantic_core
from pydantic import BaseModel

from rustic_ai.core import AgentSpec, Message
from rustic_ai.core.agents.system.models import GuildUpdatedAnnouncement
from rustic_ai.core.guild import BaseAgentProps
from rustic_ai.core.guild.agent import (
    Agent,
    AgentMode,
    AgentType,
    ProcessContext,
    processor,
)
from rustic_ai.core.guild.agent_ext.mixins.guild_refresher import GuildRefreshMixin
from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.messaging.core.message import (
    AgentTag,
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


def participant_req_filter(upa: "UserProxyAgent", message: Message) -> bool:
    return message.topic_published_to == upa.guild_requests_topic


class UserProxyAgent(Agent[UserProxyAgentProps], GuildRefreshMixin):

    BROADCAST_TOPIC = "user_message_broadcast"

    # Create a regular expression pattern from the list of usernames
    _tag_pattern = re.compile(r"(@\w+)")

    def __init__(self, agent_spec: AgentSpec[UserProxyAgentProps]):
        self.user_id = agent_spec.props.user_id
        self.user_topic = UserProxyAgent.get_user_inbox_topic(self.user_id)
        self.user_outbox_topic = UserProxyAgent.get_user_outbox_topic(self.user_id)
        self.user_notifications_topic = UserProxyAgent.get_user_notifications_topic(self.user_id)
        self.guild_notifications_topic = UserProxyAgent.get_user_system_notifications_topic(self.user_id)
        self.guild_requests_topic = UserProxyAgent.get_user_system_requests_topic(self.user_id)
        agent_spec.id = UserProxyAgent.get_user_agent_id(self.user_id)
        agent_spec.additional_topics = [
            self.user_topic,
            self.user_outbox_topic,
            UserProxyAgent.BROADCAST_TOPIC,
            self.guild_notifications_topic,
            self.guild_requests_topic,
        ]
        super().__init__(
            agent_spec=agent_spec,
            agent_type=AgentType.HUMAN,
            agent_mode=AgentMode.LOCAL,
        )

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

            # Publish the message to the notification topic so it is recorded
            # This is useful for when user fetches historical messages
            notification_rule = RoutingRule(
                agent=ctx.agent.get_agent_tag(),
                destination=RoutingDestination(
                    topics=self.user_notifications_topic,
                    priority=unwrapped_message.priority,
                    recipient_list=unwrapped_message.recipient_list + tagged_users,
                ),
            )

            ctx.add_routing_step(notification_rule)
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

    def _get_participant_list(self):
        self.guilds_agents_ats = self._get_guild_agents_ats(self.guild_spec)
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
        result = self._get_participant_list()
        routing_entry = RoutingRule(
            agent=ctx.agent.get_agent_tag(),  # TODO check what agent tag should be
            destination=RoutingDestination(
                topics=self.guild_notifications_topic,
            ),
        )
        ctx.add_routing_step(routing_entry)
        ctx.send_dict(result, format="Participants", forwarding=True)

    def find_tagged_users(self, message: str) -> List[AgentTag]:
        found_user_tags = re.findall(UserProxyAgent._tag_pattern, message)

        agent_tags = self.guilds_agents_ats.keys()
        tagged_users = [user for user in found_user_tags if user in agent_tags]

        return [self.guilds_agents_ats[tag] for tag in tagged_users]

    @processor(ParticipantListRequest, predicate=participant_req_filter)
    def handle_participants_request(self, ctx: ProcessContext[ParticipantListRequest]):
        participants = self._get_participant_list()
        routing_entry = RoutingRule(
            agent=ctx.agent.get_agent_tag(),
            destination=RoutingDestination(
                topics=self.guild_notifications_topic,
            ),
        )
        ctx.add_routing_step(routing_entry)
        ctx.send_dict(participants, format="Participants", forwarding=True)
