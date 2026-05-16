"""JIRA comment models."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JiraAddCommentRequest(BaseModel):
    """Request to add a comment to a JIRA issue."""

    issue_key: str = Field(..., description="Issue key (e.g., 'PROJ-123')")
    body: str = Field(..., description="Comment text")
    visibility: Optional[Dict[str, str]] = Field(
        None, description="Visibility restrictions (e.g., {'type': 'role', 'value': 'Administrators'})"
    )
    instance_url: str = Field(..., description="JIRA instance URL")


class JiraGetCommentsRequest(BaseModel):
    """Request to get comments for a JIRA issue."""

    issue_key: str = Field(..., description="Issue key (e.g., 'PROJ-123')")
    start_at: int = Field(default=0, description="Start index for pagination")
    max_results: int = Field(default=50, description="Maximum number of results")
    instance_url: str = Field(..., description="JIRA instance URL")


class JiraUpdateCommentRequest(BaseModel):
    """Request to update a comment on a JIRA issue."""

    issue_key: str = Field(..., description="Issue key (e.g., 'PROJ-123')")
    comment_id: str = Field(..., description="Comment ID")
    body: str = Field(..., description="Updated comment text")
    visibility: Optional[Dict[str, str]] = Field(None, description="Updated visibility restrictions")
    instance_url: str = Field(..., description="JIRA instance URL")


class JiraDeleteCommentRequest(BaseModel):
    """Request to delete a comment from a JIRA issue."""

    issue_key: str = Field(..., description="Issue key (e.g., 'PROJ-123')")
    comment_id: str = Field(..., description="Comment ID")
    instance_url: str = Field(..., description="JIRA instance URL")


class JiraCommentResponse(BaseModel):
    """Response containing comment details."""

    id: str = Field(..., description="Comment ID")
    body: str = Field(..., description="Comment text")
    author: Dict[str, Any] = Field(..., description="Comment author information")
    created: str = Field(..., description="Creation timestamp")
    updated: str = Field(..., description="Last update timestamp")
    comments: Optional[List[Dict[str, Any]]] = Field(None, description="List of comments (when getting all)")
