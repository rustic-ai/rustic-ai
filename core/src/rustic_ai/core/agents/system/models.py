from typing import List, Literal

from pydantic import BaseModel, Field

from rustic_ai.core.guild import AgentSpec
from rustic_ai.core.guild.dsl import GuildSpec


class BadInputResponse(BaseModel):
    """
    A class to represent an error when an invalid guild id is provided.
    """

    status_code: Literal[400] = 400
    status: str = Field("Bad Request")
    error_field: str
    message: str


class ConflictResponse(BaseModel):
    """
    A class to represent an error when an agent with the same id already exists.
    """

    status_code: Literal[409] = 409
    status: str = Field("Conflict")
    error_field: str
    message: str


class AgentLaunchRequest(BaseModel):
    """
    A class to represent a request to add an agent to the guild.
    """

    agent_spec: AgentSpec


class AgentLaunchResponse(BaseModel):
    """
    A class to represent the response to a request to add an agent to the guild.
    """

    agent_id: str
    status_code: int
    status: str


class AgentListRequest(BaseModel):
    """
    A class to represent a request to list the agents in the guild.
    """

    guild_id: str


class RunningAgentListRequest(BaseModel):
    """
    A class to represent a request to list the running agents in the guild.
    """

    guild_id: str


class AgentGetRequest(BaseModel):
    """
    A class to represent a request to get an agent in the guild.
    """

    guild_id: str
    agent_id: str


class UserAgentCreationRequest(BaseModel):
    """
    A class to represent a request to create a user agent.
    """

    user_id: str
    user_name: str


class UserAgentCreationResponse(BaseModel):
    """
    A class to represent the response to a request to add an agent to the guild.
    """

    user_id: str
    agent_id: str
    status_code: int
    status: str
    topic: str


class UserAgentGetRequest(BaseModel):
    """
    A class to represent a request to get a user agent.
    """

    user_id: str


class AgentInfoResponse(BaseModel):
    """
    A class to represent a member of the guild.
    """

    id: str
    name: str
    description: str
    class_name: str


class AgentListResponse(BaseModel):
    """
    A class to represent the response to a request to list the agents in the guild.
    """

    agents: List[AgentInfoResponse]


class GuildUpdatedAnnouncement(BaseModel):
    """
    A class to represent an announcement that the guild has been updated.
    """

    guild_id: str
    guild_spec: GuildSpec
