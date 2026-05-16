"""Slack user models."""

from typing import List, Optional

from pydantic import BaseModel, Field


class SlackGetUserInfoRequest(BaseModel):
    """Get information about a user."""

    workspace_id: str = Field(..., description="Slack workspace/team ID")
    user_id: str = Field(..., description="User ID")


class SlackListUsersRequest(BaseModel):
    """List all users in workspace."""

    workspace_id: str = Field(..., description="Slack workspace/team ID")
    limit: int = Field(100, description="Max users per request", ge=1, le=1000)
    cursor: Optional[str] = Field(None, description="Pagination cursor")


class SlackUserProfile(BaseModel):
    """User profile information."""

    display_name: str
    real_name: str
    email: Optional[str] = None
    image_24: Optional[str] = None
    image_48: Optional[str] = None
    image_72: Optional[str] = None
    status_text: Optional[str] = None
    status_emoji: Optional[str] = None


class SlackUser(BaseModel):
    """Represents a Slack user."""

    id: str = Field(..., description="User ID")
    name: str = Field(..., description="Username")
    profile: SlackUserProfile = Field(..., description="User profile")
    is_bot: bool = Field(..., description="Is a bot user")
    is_admin: bool = Field(False, description="Is workspace admin")
    deleted: bool = Field(False, description="User is deleted/deactivated")


class SlackUsersResponse(BaseModel):
    """Response containing multiple users."""

    users: List[SlackUser] = Field(..., description="List of users")
    has_more: bool = Field(..., description="Whether more users exist")
    next_cursor: Optional[str] = Field(None, description="Cursor for next page")
