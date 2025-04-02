from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field

from ..utils.json_utils import JsonDict


class StateOwner(StrEnum):
    """
    An enumeration of the owners of the state.
    """

    AGENT = "agent"
    GUILD = "guild"


class StateUpdateFormat(StrEnum):
    """
    An enumeration of the formats that state updates can be sent in.
    Currently we support JSON Patch (https://datatracker.ietf.org/doc/html/rfc6902) and
    JSON Merge Patch (https://datatracker.ietf.org/doc/html/rfc7386) is supported.
    In future we will support crdt and other formats based on requirements.
    """

    JSON_PATCH = "json-patch"
    JSON_MERGE_PATCH = "json-merge-patch"


class StateFetchRequest(BaseModel):
    """
    A class to represent a request to get the state of the guild or an agent.
    """

    state_owner: StateOwner = Field(
        description="The owner of the state. The owner can be an agent or the guild.",
    )

    guild_id: str = Field(
        description="The ID of the guild to which the state belongs.",
    )

    agent_id: Optional[str] = Field(
        default=None,
        description="""The ID of the agent to get the state of. It will be used if state owner is agent.
        Will fetch the calling agent's state if not provided. Will fail if calling agent does not have access to the target agent.""",
    )
    state_path: Optional[str] = Field(
        default=None,
        description="The path on the state object to read. Will return the entire state object if not provided.",
    )
    version: Optional[int] = Field(
        default=None,
        description="The version of the state to read. Will return the latest version if not provided.",
    )
    timestamp: Optional[int] = Field(
        default=None,
        description="""The timestamp of the state to read. Will provide the latest state before the timestamp if there is no exact match.
        Will return the latest version if not provided.""",
    )


class StateFetchResponse(BaseModel):
    """
    A class to represent the the state of an agent or the guild.
    """

    state_owner: StateOwner = Field(
        description="The owner of the state. The owner can be an agent or the guild.",
    )

    guild_id: str = Field(
        description="The ID of the guild from which the state was fetched.",
    )

    agent_id: Optional[str] = Field(
        default=None,
        description="The ID of the agent to which the state belongs. None if the state belongs to the guild.",
    )

    state: JsonDict = Field(
        default_factory=dict,
        description="The state of the agent or guild. The structure of the state is defined by the agent or guild.",
    )
    version: int = Field(
        description="The version of the state. The version is incremented every time the state is updated.",
    )
    timestamp: int = Field(
        description="The timestamp of the state. The timestamp is the time the state was last updated.",
    )
    state_path: Optional[str] = Field(
        default=None,
        description="The path on the state object that was read. None if the entire state object was read.",
    )
    fetch_timestamp: int = Field(
        description="""The timestamp of the state that was read.
        This is the timestamp of the state that was read, which may be different from the requested timestamp.""",
    )
    is_latest: bool = Field(
        description="True if the state is the latest state, False otherwise.",
    )


class StateFetchError(BaseModel):
    """
    A class to represent an error that occurred while fetching the state.
    """

    state_fetch_request: StateFetchRequest = Field(
        description="The state fetch request that failed.",
    )

    error: str = Field(
        description="The error message.",
    )


class StateUpdateRequest(BaseModel):
    """
    A class to represent a request to update the state of the guild or an agent.
    """

    state_owner: StateOwner = Field(
        description="The owner of the state. The owner can be an agent or the guild.",
    )

    guild_id: str = Field(
        description="The ID of the guild to which the state belongs.",
    )

    agent_id: Optional[str] = Field(
        default=None,
        description="The ID of the agent to which the state belongs. None if the state belongs to the guild.",
    )

    update_format: StateUpdateFormat = Field(
        default=StateUpdateFormat.JSON_MERGE_PATCH,
        description="""The format of the state update. Currently we support JSON Patch (https://datatracker.ietf.org/doc/html/rfc6902)
        and JSON Merge Patch (https://datatracker.ietf.org/doc/html/rfc7386) is supported.""",
    )

    state_update: JsonDict = Field(
        description="The update payload. The structure of the payload is defined by the update format.",
    )

    update_path: Optional[str] = Field(
        default=None,
        description="The path on the state object to update. Will apply update at the root of the state object if not provided.",
    )

    update_version: Optional[int] = Field(
        default=None,
        description="""The version of the state to update. Will fail if the version does not match the latest version.
        Will update the latest version if not provided.""",
    )

    update_timestamp: Optional[int] = Field(
        default=None,
        description="""The timestamp of the state to update. Will fail if the timestamp does not match the latest timestamp.
        Will update the latest version if not provided.""",
    )


class StateUpdateResponse(BaseModel):
    """
    A class to represent the response to a state update request.
    """

    state_owner: StateOwner = Field(
        description="The owner of the state. The owner can be an agent or the guild.",
    )

    guild_id: str = Field(
        description="The ID of the guild to which the state belongs.",
    )

    agent_id: Optional[str] = Field(
        default=None,
        description="The ID of the agent to which the state belongs. None if the state belongs to the guild.",
    )

    state: JsonDict = Field(
        default_factory=dict,
        description="The updated state of the agent or guild. The structure of the state is defined by the agent or guild.",
    )

    version: int = Field(
        description="The version of the state. The version is incremented every time the state is updated.",
    )

    timestamp: int = Field(
        description="The timestamp of the state. The timestamp is the time the state was last updated.",
    )


class StateUpdateError(BaseModel):
    """
    A class to represent an error that occurred while updating the state.
    """

    state_update_request: StateUpdateRequest = Field(
        description="The state update request that failed.",
    )

    error: str = Field(
        description="The error message.",
    )
