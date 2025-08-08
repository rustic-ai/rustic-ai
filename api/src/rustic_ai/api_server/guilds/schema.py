from pydantic import BaseModel

from rustic_ai.core.guild.dsl import GuildSpec
from rustic_ai.core.guild.metastore.models import GuildStatus


class IdInfo(BaseModel):
    id: str


class LaunchGuildReq(BaseModel):
    spec: GuildSpec
    org_id: str


class GuildSpecResponse(GuildSpec):
    """
    Response for a guild specification that describes its name, description, agents, routes, and status.
    """

    status: GuildStatus


class RelaunchResponse(BaseModel):
    is_relaunching: bool
