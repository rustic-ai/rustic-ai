from datetime import datetime
from enum import Enum
import logging
from typing import Dict

from pydantic import (
    BaseModel,
    Field,
    JsonValue,
    SerializationInfo,
    computed_field,
    field_serializer,
)

from rustic_ai.core.guild import agent
from rustic_ai.core.guild.dsl import GuildTopics
from rustic_ai.core.utils.basic_class_utils import get_qualified_class_name
from rustic_ai.core.utils.priority import Priority


class HealthCheckRequest(BaseModel):
    checktime: datetime = Field(default_factory=datetime.now)

    @field_serializer("checktime")
    def serialize_checktime(self, v: datetime, info: SerializationInfo) -> str:
        return v.isoformat()


class HeartbeatStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    BACKLOGGED = "backlogged"
    UNKNOWN = "unknown"
    STARTING = "starting"
    PENDING_LAUNCH = "pending_launch"


class Heartbeat(BaseModel):
    checktime: datetime
    checkstatus: HeartbeatStatus
    responsetime: datetime = Field(default_factory=datetime.now)
    checkmeta: Dict[str, JsonValue] = {}

    @field_serializer("checktime")
    def serialize_checktime(self, v: datetime, info: SerializationInfo) -> str:
        return v.isoformat()

    @field_serializer("responsetime")
    def serialize_responsetime(self, v: datetime, info: SerializationInfo) -> str:
        return v.isoformat()


class AgentsHealthReport(BaseModel):
    agents: Dict[str, Heartbeat] = Field(default_factory=dict)

    @computed_field  # type: ignore[misc]
    @property
    def guild_health(self) -> HeartbeatStatus:
        if not self.agents:
            return HeartbeatStatus.UNKNOWN
        statuses = [agent.checkstatus for agent in self.agents.values()]
        if all(status == HeartbeatStatus.OK for status in statuses):
            return HeartbeatStatus.OK
        if any(status == HeartbeatStatus.ERROR for status in statuses):
            return HeartbeatStatus.ERROR
        if any(status == HeartbeatStatus.BACKLOGGED for status in statuses):
            return HeartbeatStatus.BACKLOGGED
        if any(status == HeartbeatStatus.WARNING for status in statuses):
            return HeartbeatStatus.WARNING
        if any(status == HeartbeatStatus.UNKNOWN for status in statuses):
            return HeartbeatStatus.UNKNOWN
        if any(status == HeartbeatStatus.STARTING for status in statuses):
            return HeartbeatStatus.STARTING
        return HeartbeatStatus.UNKNOWN

    @field_serializer("agents")
    def serialize_agents(self, v: Dict[str, Heartbeat], info: SerializationInfo) -> Dict[str, JsonValue]:
        return {k: v.model_dump() for k, v in v.items()}


class HealthConstants:
    HEARTBEAT_TOPIC = "heartbeat"


if HealthConstants.HEARTBEAT_TOPIC not in GuildTopics.ESSENTIAL_TOPICS:
    GuildTopics.ESSENTIAL_TOPICS.append(HealthConstants.HEARTBEAT_TOPIC)


class HealthMixin:

    @agent.processor(HealthCheckRequest, handle_essential=True)
    def send_heartbeat(self, ctx: agent.ProcessContext[HealthCheckRequest]):
        hr = self.healthcheck(ctx.payload.checktime)
        ctx._direct_send(
            priority=Priority.HIGH,
            topics=[HealthConstants.HEARTBEAT_TOPIC],
            payload=hr.model_dump(),
            format=get_qualified_class_name(Heartbeat),
            recipient_list=[],
            in_response_to=ctx.message.id,
        )

    def healthcheck(self, checktime: datetime) -> Heartbeat:

        checkmeta: dict = {}
        if isinstance(self, agent.Agent):
            logging.info(f"Healthcheck for {self.get_agent_tag()}")
            status = HeartbeatStatus.OK
            checkmeta = {}
            if isinstance(self, agent.Agent):
                qos_latency = self.agent_spec.qos.latency
                time_now = datetime.now()
                msg_latency = (time_now - checktime).total_seconds() * 1000  # Convert to milliseconds
                if qos_latency and msg_latency > qos_latency:
                    status = HeartbeatStatus.BACKLOGGED

                checkmeta["qos_latency"] = qos_latency

            checkmeta["observed_latency"] = msg_latency

        return Heartbeat(checktime=checktime, checkstatus=status, checkmeta=checkmeta)

    @agent.processor(
        agent.SelfReadyNotification,
        predicate=lambda self, msg: msg.sender == self.get_agent_tag() and msg.topic_published_to == self._self_inbox,
        handle_essential=True,
    )
    def send_first_heartbeat(self, ctx: agent.ProcessContext[agent.SelfReadyNotification]):
        """
        Sends the first heartbeat when the agent is ready.
        """
        if not isinstance(self, agent.Agent):
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
        )
