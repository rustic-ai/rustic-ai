"""Slack message models."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from rustic_ai.core.utils.json_utils import JsonDict

# Request Models


class SlackSendMessageRequest(BaseModel):
    """Send a message to a Slack channel."""

    workspace_id: str = Field(..., description="Slack workspace/team ID")
    channel: str = Field(..., description="Channel ID or name (e.g., 'C123456' or '#general')")
    text: str = Field(..., description="Message text (max 12,000 chars)")
    thread_ts: Optional[str] = Field(None, description="Parent message timestamp for threading")
    blocks: Optional[List[JsonDict]] = Field(None, description="Block Kit structured blocks")
    reply_broadcast: bool = Field(False, description="Broadcast thread reply to channel")
    username: Optional[str] = Field(None, description="Custom bot username")
    icon_url: Optional[str] = Field(None, description="Custom bot icon URL")
    icon_emoji: Optional[str] = Field(None, description="Custom bot emoji")
    metadata: Optional[JsonDict] = Field(None, description="Message metadata")


class SlackUpdateMessageRequest(BaseModel):
    """Update an existing message."""

    workspace_id: str = Field(..., description="Slack workspace/team ID")
    channel: str = Field(..., description="Channel ID containing the message")
    ts: str = Field(..., description="Timestamp of message to update")
    text: str = Field(..., description="New message text")
    blocks: Optional[List[JsonDict]] = Field(None, description="New Block Kit blocks")


class SlackDeleteMessageRequest(BaseModel):
    """Delete a message."""

    workspace_id: str = Field(..., description="Slack workspace/team ID")
    channel: str = Field(..., description="Channel ID containing the message")
    ts: str = Field(..., description="Timestamp of message to delete")


class SlackGetMessagesRequest(BaseModel):
    """Fetch message history from a channel."""

    workspace_id: str = Field(..., description="Slack workspace/team ID")
    channel: str = Field(..., description="Channel ID")
    limit: int = Field(100, description="Number of messages to retrieve", ge=1, le=1000)
    cursor: Optional[str] = Field(None, description="Pagination cursor")
    oldest: Optional[str] = Field(None, description="Start of time range (timestamp)")
    newest: Optional[str] = Field(None, description="End of time range (timestamp)")
    inclusive: bool = Field(False, description="Include messages with oldest/newest timestamps")


class SlackGetThreadRepliesRequest(BaseModel):
    """Fetch replies in a thread."""

    workspace_id: str = Field(..., description="Slack workspace/team ID")
    channel: str = Field(..., description="Channel ID")
    thread_ts: str = Field(..., description="Thread parent timestamp")
    cursor: Optional[str] = Field(None, description="Pagination cursor")
    limit: int = Field(100, description="Number of replies to retrieve", ge=1, le=1000)


# Response Models


class SlackMessage(BaseModel):
    """Represents a Slack message."""

    ts: str = Field(..., description="Message timestamp (unique ID)")
    user: Optional[str] = Field(None, description="User ID who sent the message")
    text: str = Field(..., description="Message text")
    channel: str = Field(..., description="Channel ID")
    thread_ts: Optional[str] = Field(None, description="Parent thread timestamp")
    reply_count: Optional[int] = Field(None, description="Number of replies")
    reactions: Optional[List[Dict[str, Any]]] = Field(None, description="Message reactions")
    files: Optional[List[Dict[str, Any]]] = Field(None, description="Attached files")
    blocks: Optional[List[JsonDict]] = Field(None, description="Block Kit blocks")
    metadata: Optional[JsonDict] = Field(None, description="Message metadata")


class SlackSendMessageResponse(BaseModel):
    """Response after sending a message."""

    channel: str = Field(..., description="Channel ID where message was posted")
    ts: str = Field(..., description="Message timestamp")
    message: SlackMessage = Field(..., description="Complete message object")


class SlackMessagesResponse(BaseModel):
    """Response containing multiple messages."""

    channel: str = Field(..., description="Channel ID")
    messages: List[SlackMessage] = Field(..., description="List of messages")
    has_more: bool = Field(..., description="Whether more messages exist")
    next_cursor: Optional[str] = Field(None, description="Cursor for next page")
