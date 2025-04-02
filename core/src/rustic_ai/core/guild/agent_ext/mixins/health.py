from datetime import datetime
from typing import Dict

from pydantic import BaseModel, JsonValue, SerializationInfo, field_serializer

from rustic_ai.core.guild import agent
from rustic_ai.core.guild.dsl import GuildTopics


class Heartbeat(BaseModel):
    checktime: datetime

    @field_serializer("checktime")
    def serialize_checktime(self, v: datetime, info: SerializationInfo) -> str:
        return v.isoformat()


class HeartbeatResponse(BaseModel):
    checktime: datetime
    checkstatus: str
    checkmeta: Dict[str, JsonValue] = {}

    @field_serializer("checktime")
    def serialize_checktime(self, v: datetime, info: SerializationInfo) -> str:
        return v.isoformat()


class HealthConstants:
    HEARTBEAT_TOPIC = "heartbeat"


if HealthConstants.HEARTBEAT_TOPIC not in GuildTopics.ESSENTIAL_TOPICS:
    GuildTopics.ESSENTIAL_TOPICS.append(HealthConstants.HEARTBEAT_TOPIC)


class HealthMixin:

    @agent.processor(Heartbeat, handle_essential=True)
    def send_heartbeat(self, context: agent.ProcessContext[Heartbeat]):
        hr = self.healthcheck(context.payload.checktime)
        context.send(hr)

    def healthcheck(self, checktime: datetime) -> HeartbeatResponse:
        return HeartbeatResponse(checktime=checktime, checkstatus="OK", checkmeta={})
