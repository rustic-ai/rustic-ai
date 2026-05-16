"""Slack reaction models."""

from typing import List

from pydantic import BaseModel, Field


class SlackAddReactionRequest(BaseModel):
    """Add a reaction to a message."""

    workspace_id: str = Field(..., description="Slack workspace/team ID")
    channel: str = Field(..., description="Channel ID")
    timestamp: str = Field(..., description="Message timestamp")
    name: str = Field(..., description="Emoji name without colons (e.g., 'thumbsup')")


class SlackGetReactionsRequest(BaseModel):
    """Get reactions for a message."""

    workspace_id: str = Field(..., description="Slack workspace/team ID")
    channel: str = Field(..., description="Channel ID")
    timestamp: str = Field(..., description="Message timestamp")


class SlackReaction(BaseModel):
    """Represents a reaction."""

    name: str = Field(..., description="Emoji name")
    count: int = Field(..., description="Reaction count")
    users: List[str] = Field(..., description="User IDs who reacted")


class SlackReactionsResponse(BaseModel):
    """Response containing reactions."""

    channel: str
    timestamp: str
    reactions: List[SlackReaction]
