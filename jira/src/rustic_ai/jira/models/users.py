"""JIRA user models."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JiraGetUserRequest(BaseModel):
    """Request to get a JIRA user by username or account ID."""

    username: Optional[str] = Field(None, description="Username (for Jira Server/Data Center)")
    account_id: Optional[str] = Field(None, description="Account ID (for Jira Cloud)")
    instance_url: str = Field(..., description="JIRA instance URL")


class JiraSearchUsersRequest(BaseModel):
    """Request to search for JIRA users."""

    query: str = Field(..., description="Search query string")
    max_results: int = Field(default=50, description="Maximum number of results")
    start_at: int = Field(default=0, description="Start index for pagination")
    instance_url: str = Field(..., description="JIRA instance URL")


class JiraUserResponse(BaseModel):
    """Response containing user details."""

    account_id: Optional[str] = Field(None, description="User account ID")
    display_name: str = Field(..., description="User display name")
    email_address: Optional[str] = Field(None, description="User email")
    active: bool = Field(..., description="Whether user is active")
    avatar_urls: Optional[Dict[str, str]] = Field(None, description="Avatar URLs")


class JiraUsersResponse(BaseModel):
    """Response containing list of users."""

    users: List[Dict[str, Any]] = Field(..., description="List of users")
    total: int = Field(..., description="Total number of users")
