"""Slack file models."""

from typing import List, Optional

from pydantic import BaseModel, Field


class SlackUploadFileRequest(BaseModel):
    """Upload a file to Slack (using 2-step process)."""

    workspace_id: str = Field(..., description="Slack workspace/team ID")
    channels: List[str] = Field(..., description="Channel IDs to share file in")
    content: bytes = Field(..., description="File content")
    filename: str = Field(..., description="Filename")
    title: Optional[str] = Field(None, description="File title")
    initial_comment: Optional[str] = Field(None, description="Initial comment")
    thread_ts: Optional[str] = Field(None, description="Thread timestamp")


class SlackGetFileInfoRequest(BaseModel):
    """Get information about a file."""

    workspace_id: str = Field(..., description="Slack workspace/team ID")
    file_id: str = Field(..., description="File ID")


class SlackDeleteFileRequest(BaseModel):
    """Delete a file."""

    workspace_id: str = Field(..., description="Slack workspace/team ID")
    file_id: str = Field(..., description="File ID")


class SlackFile(BaseModel):
    """Represents a Slack file."""

    id: str = Field(..., description="File ID")
    name: str = Field(..., description="Filename")
    title: Optional[str] = Field(None, description="File title")
    mimetype: str = Field(..., description="MIME type")
    size: int = Field(..., description="File size in bytes")
    url_private: Optional[str] = Field(None, description="Private download URL")
    url_private_download: Optional[str] = Field(None, description="Direct download URL")
    user: Optional[str] = Field(None, description="User ID who uploaded")
    created: int = Field(..., description="Unix timestamp of creation")


class SlackFileUploadResponse(BaseModel):
    """Response after file upload."""

    file: SlackFile = Field(..., description="Uploaded file object")
