"""JIRA attachment models."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class JiraAddAttachmentRequest(BaseModel):
    """Request to add an attachment to a JIRA issue."""

    issue_key: str = Field(..., description="Issue key (e.g., 'PROJ-123')")
    filename: str = Field(..., description="Attachment filename")
    content: bytes = Field(..., description="Attachment content")
    instance_url: str = Field(..., description="JIRA instance URL")


class JiraGetAttachmentRequest(BaseModel):
    """Request to get attachment metadata."""

    attachment_id: str = Field(..., description="Attachment ID")
    instance_url: str = Field(..., description="JIRA instance URL")


class JiraDeleteAttachmentRequest(BaseModel):
    """Request to delete an attachment."""

    attachment_id: str = Field(..., description="Attachment ID")
    instance_url: str = Field(..., description="JIRA instance URL")


class JiraAttachmentResponse(BaseModel):
    """Response containing attachment details."""

    id: str = Field(..., description="Attachment ID")
    filename: str = Field(..., description="Attachment filename")
    author: Dict[str, Any] = Field(..., description="Author information")
    created: str = Field(..., description="Creation timestamp")
    size: int = Field(..., description="File size in bytes")
    mime_type: str = Field(..., description="MIME type")
    content_url: str = Field(..., description="Content download URL")
