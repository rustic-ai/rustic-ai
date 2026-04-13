"""Slack channel models."""

from typing import List, Optional

from pydantic import BaseModel, Field


class SlackCreateChannelRequest(BaseModel):
    """Create a new channel."""

    workspace_id: str = Field(..., description="Slack workspace/team ID")
    name: str = Field(..., description="Channel name (lowercase, no spaces)")
    is_private: bool = Field(False, description="Create as private channel")
    description: Optional[str] = Field(None, description="Channel description")


class SlackListChannelsRequest(BaseModel):
    """List all channels."""

    workspace_id: str = Field(..., description="Slack workspace/team ID")
    types: List[str] = Field(
        default_factory=lambda: ["public_channel"],
        description="Channel types: public_channel, private_channel, im, mpim",
    )
    exclude_archived: bool = Field(True, description="Exclude archived channels")
    limit: int = Field(100, description="Max channels per request", ge=1, le=1000)
    cursor: Optional[str] = Field(None, description="Pagination cursor")


class SlackJoinChannelRequest(BaseModel):
    """Join a channel."""

    workspace_id: str = Field(..., description="Slack workspace/team ID")
    channel: str = Field(..., description="Channel ID or name")


class SlackInviteToChannelRequest(BaseModel):
    """Invite users to a channel."""

    workspace_id: str = Field(..., description="Slack workspace/team ID")
    channel: str = Field(..., description="Channel ID")
    users: List[str] = Field(..., description="List of user IDs to invite")


class SlackChannel(BaseModel):
    """Represents a Slack channel."""

    id: str = Field(..., description="Channel ID")
    name: str = Field(..., description="Channel name")
    is_channel: bool = Field(..., description="Is a channel (not DM/group)")
    is_private: bool = Field(..., description="Is a private channel")
    is_archived: bool = Field(..., description="Is archived")
    is_member: bool = Field(..., description="Bot is a member")
    topic: Optional[str] = Field(None, description="Channel topic")
    purpose: Optional[str] = Field(None, description="Channel purpose")
    num_members: Optional[int] = Field(None, description="Number of members")


class SlackChannelsResponse(BaseModel):
    """Response containing multiple channels."""

    channels: List[SlackChannel] = Field(..., description="List of channels")
    has_more: bool = Field(..., description="Whether more channels exist")
    next_cursor: Optional[str] = Field(None, description="Cursor for next page")
