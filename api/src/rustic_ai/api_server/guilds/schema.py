from pydantic import BaseModel

from rustic_ai.core.guild.dsl import GuildSpec


class IdInfo(BaseModel):
    id: str


class LaunchGuildReq(BaseModel):
    spec: GuildSpec
    org_id: str
